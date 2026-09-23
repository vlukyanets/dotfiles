"""Dotfiles: home/ rendered with a host's resolved config."""

import json
import os
import re
import shutil
import tempfile
import tomllib
import traceback
from pathlib import Path

import jinja2
import tomli_w

from dotfiles import config
from dotfiles.config import ROOT, ConfigError

SUFFIX = ".j2"
DEFAULT_MODE = {False: 0o644, True: 0o755}  # by is_dir


class TemplateFail(Exception):
    """Raised by fail() in a template: the data is wrong for this host."""


def fail(message: str):
    raise TemplateFail(message)


def from_toml(text: str) -> dict:
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise TemplateFail(f"not valid TOML: {e}") from None


def merge_over(want: dict, base: dict) -> dict:
    """BASE with WANT's keys on top, tables merged recursively: what an
    application wrote survives unless the repo sets that key."""
    out = dict(base)
    for key, value in want.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            value = merge_over(value, base[key])
        out[key] = value
    return out


def regex_search(text: str, pattern: str) -> str:
    """The first group of the first match (the whole match without groups), or ""."""
    m = re.search(pattern, text)
    return "" if m is None else m.group(1 if m.groups() else 0)


def environment(home: Path) -> jinja2.Environment:
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(home),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.globals["fail"] = fail
    # Go's %q, which chezmoi's templates used: a double-quoted string that is
    # also valid TOML and JSON.
    env.filters["quote"] = lambda s: json.dumps(str(s), ensure_ascii=False)
    # Ansible's extract: names | map("extract", registry) looks each name up.
    env.filters["extract"] = lambda key, container: container[key]
    # For files an application rewrites itself: merge with `current`.
    env.filters["from_toml"] = from_toml
    env.filters["to_toml"] = tomli_w.dumps
    env.filters["merge_over"] = merge_over
    env.filters["regex_search"] = regex_search
    return env


def manifest(root: Path) -> dict[str, dict]:
    """home.toml: path under home/ -> {mode: int, when: str}, checked."""
    path = root / "home.toml"
    if not path.exists():
        return {}
    entries = config.load(path, root)
    for rel, entry in entries.items():
        where = f"home.toml: {rel}"
        if not isinstance(entry, dict) or set(entry) - {"mode", "when"}:
            raise ConfigError(f"{where}: only mode and when are allowed")
        home = root / "home"
        if not ((home / rel).exists() or (home / (rel + SUFFIX)).exists()):
            raise ConfigError(f"{where}: no such file or directory under home/")
        if "mode" in entry:
            mode = entry["mode"]
            if not isinstance(mode, str) or len(mode) != 3 or set(mode) - set("01234567"):
                raise ConfigError(f'{where}: mode must be three octal digits, like "600"')
            entry["mode"] = int(mode, 8)
        if not isinstance(entry.get("when", ""), str):
            raise ConfigError(f"{where}: when must be a string")
    return entries


# Registry in data/ -> the config key whose names must all be in it.
REFERENCES = {"languages": "features.locale.languages", "ssh_keys": "ssh.authorized_keys"}


def registries(host: str, cfg: dict, root: Path) -> dict:
    """data/*.toml merged, after checking every name CFG takes from them."""
    merged = {}
    for path in sorted((root / "data").glob("*.toml")):
        merged |= config.load(path, root)
    for registry, dotted in REFERENCES.items():
        names = cfg
        for key in dotted.split("."):
            names = names.get(key, {})
        for name in names or []:
            if name not in merged.get(registry, {}):
                raise ConfigError(f"{host}: {dotted}: {name!r} is not in data/ ({registry})")
    return merged


def _error(e: Exception, template: str, host: str) -> ConfigError:
    """The template's name and line, and the host, for any error raised while rendering."""
    line = getattr(e, "lineno", None)
    for frame in traceback.extract_tb(e.__traceback__):
        if frame.filename.endswith(template):
            line = frame.lineno
    where = f"home/{template}" + (f":{line}" if line else "")
    return ConfigError(f"{where}: {host}: {getattr(e, 'message', None) or e}")


def render(host: str, out: Path, root: Path = ROOT, current: Path | None = None) -> list[str]:
    """Write HOST's home tree into OUT, which must be missing or empty.

    CURRENT is the home directory whose files merged templates read as
    `current`; without it they see an empty file. Returns the paths written,
    relative to OUT.
    """
    if out.exists() and any(out.iterdir()):
        raise ConfigError(f"{out}: not empty")
    home = root / "home"
    if not home.is_dir():
        return []
    entries = manifest(root)
    env = environment(home)
    cfg = config.resolve(host, root)
    context = (
        cfg
        | registries(host, cfg, root)
        | {
            "host": host,
            "home": str(Path.home()),
            "uid": os.getuid(),
        }
    )

    def enabled(rel: Path) -> bool:
        # A gate on a directory covers everything under it.
        for part in [rel, *rel.parents][:-1]:
            when = entries.get(part.as_posix(), {}).get("when")
            if when is None:
                continue
            try:
                if not env.compile_expression(when, undefined_to_none=False)(**context):
                    return False
            except jinja2.TemplateError as e:
                raise ConfigError(f"home.toml: {part.as_posix()}: when: {host}: {e}") from None
        return True

    written = []
    out.mkdir(parents=True, exist_ok=True)
    for src in sorted(home.rglob("*")):
        is_template = src.is_file() and src.name.endswith(SUFFIX)
        rel = src.relative_to(home)
        if is_template:
            rel = rel.with_name(rel.name.removesuffix(SUFFIX))
        if not enabled(rel):
            continue
        dst = out / rel
        mode = entries.get(rel.as_posix(), {}).get("mode", DEFAULT_MODE[src.is_dir()])
        if src.is_dir():
            dst.mkdir(exist_ok=True)
        elif is_template:
            name = src.relative_to(home).as_posix()
            cur = current / rel if current else None
            try:
                text = env.get_template(name).render(
                    context, current=cur.read_text() if cur and cur.is_file() else ""
                )
            except (jinja2.TemplateError, TemplateFail) as e:
                raise _error(e, name, host) from None
            dst.write_text(text)
        else:
            shutil.copyfile(src, dst)
        dst.chmod(mode)
        written.append(rel.as_posix())
    return written


def check(root: Path = ROOT) -> dict[str, str | None]:
    """config.check, then every host that resolves is rendered into a temp dir."""
    results = config.check(root)
    for host, error in results.items():
        if error is None:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    render(host, Path(tmp) / "home", root)
                except ConfigError as e:
                    results[host] = str(e)
    return results
