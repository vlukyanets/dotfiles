"""Dotfiles: home/ rendered with a host's resolved config."""

import json
import os
import re
import shutil
import socket
import stat
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
    # A double-quoted string that is also valid TOML and JSON.
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


def render(
    host: str,
    out: Path,
    root: Path = ROOT,
    current: Path | None = None,
    cfg: dict | None = None,
) -> list[str]:
    """Write HOST's home tree into OUT, which must be missing or empty.

    CURRENT is the home directory whose files merged templates read as
    `current`; without it they see an empty file. CFG is HOST's config,
    resolved from ROOT when not given. Returns the paths written, relative
    to OUT.
    """
    if out.exists() and any(out.iterdir()):
        raise ConfigError(f"{out}: not empty")
    home = root / "home"
    if not home.is_dir():
        return []
    entries = manifest(root)
    env = environment(home)
    cfg = config.resolve(host, root) if cfg is None else cfg
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


def check(root: Path = ROOT, source: Path | None = None) -> dict[str, str | None]:
    """config.check of SOURCE (default ROOT), plus the machine config as
    "local" when there is one; everything that resolves has its features'
    requirements checked on every platform and is rendered into a temp dir
    with the templates of ROOT."""
    from dotfiles import apply  # apply deploys through this module

    source = source or root
    results = config.check(source)
    local = config.local_path()
    if local.exists():
        results["local"] = None
    for host, error in results.items():
        if error is None:
            with tempfile.TemporaryDirectory() as tmp:
                try:
                    if host == "local":
                        name = socket.gethostname()
                        cfg = config.resolve(name, root, local)
                    else:
                        name, cfg = host, config.resolve(host, source)
                    apply.requirements(cfg)
                    render(name, Path(tmp) / "home", root, cfg=cfg)
                except ConfigError as e:
                    results[host] = str(e)
    return results


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def deploy(
    host: str,
    root: Path = ROOT,
    home: Path | None = None,
    dry_run: bool = False,
    cfg: dict | None = None,
) -> list[str]:
    """Bring HOME in line with HOST's rendered tree (CFG as in render);
    returns one line per change.

    Only what differs is written, file by file through a temp file and a
    rename; nothing is ever deleted. Directories get their mode when they are
    created, and later only when home.toml sets one. A clean HOME yields [].
    """
    home = home or Path.home()
    real_home = home.resolve()
    entries = manifest(root)
    changes = []
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / "home"
        for rel in render(host, staged, root, current=home, cfg=cfg):
            src, dst = staged / rel, home / rel
            # A symlinked directory on the way must not lead out of HOME.
            if not dst.parent.resolve().is_relative_to(real_home):
                raise ConfigError(f"~/{rel}: {dst.parent} leads outside {home}")
            want = _mode(src)
            if src.is_dir():
                if dst.is_dir():
                    if "mode" not in entries.get(rel, {}) or _mode(dst) == want:
                        continue
                    why = f"mode {_mode(dst):o}"
                elif dst.exists():
                    raise ConfigError(f"~/{rel}: exists and is not a directory")
                else:
                    why = "missing"
                if not dry_run:
                    dst.mkdir(exist_ok=True)
                    dst.chmod(want)
            else:
                if dst.is_dir():
                    raise ConfigError(f"~/{rel}: is a directory")
                content = src.read_bytes()
                if not dst.exists():
                    why = "missing"
                elif dst.read_bytes() != content:
                    why = "content differs"
                elif _mode(dst) != want:
                    why = f"mode {_mode(dst):o}"
                else:
                    continue
                if not dry_run:
                    fd, part = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.")
                    with os.fdopen(fd, "wb") as f:
                        f.write(content)
                    os.chmod(part, want)
                    os.replace(part, dst)
            changes.append(f"-> ~/{rel} ({why})")
    return changes
