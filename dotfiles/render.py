import json
import os
import re
import shutil
import stat
import tempfile
import tomllib
import traceback
from pathlib import Path

import jinja2
import tomli_w

from dotfiles import config, engine
from dotfiles.config import merge_over
from dotfiles.errors import ConfigError
from dotfiles.layout import Layout

_SUFFIX = ".j2"
_DEFAULT_MODE = {False: 0o644, True: 0o755}  # by is_dir


class _TemplateFail(Exception):
    """Raised by fail() in a template: the data is wrong for this host."""


def _fail(message: str):
    """fail(message) in a template: stop rendering with MESSAGE."""
    raise _TemplateFail(message)


def _from_toml(text: str) -> dict:
    """TEXT parsed as TOML; an error fails the template."""
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise _TemplateFail(f"not valid TOML: {e}") from None


def regex_search(text: str, pattern: str) -> str:
    """The first group of the first match (the whole match without groups), or ""."""
    m = re.search(pattern, text)
    return "" if m is None else m.group(1 if m.groups() else 0)


def _environment(home: Path) -> jinja2.Environment:
    """Jinja2 for templates under HOME, with this project's filters."""
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(home),
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
        trim_blocks=True,
        lstrip_blocks=True,
        autoescape=False,
    )
    env.globals["fail"] = _fail
    # A double-quoted string that is also valid TOML and JSON.
    env.filters["quote"] = lambda s: json.dumps(str(s), ensure_ascii=False)
    # For files an application rewrites itself: merge with `current`.
    env.filters["from_toml"] = _from_toml
    env.filters["to_toml"] = tomli_w.dumps
    env.filters["merge_over"] = merge_over
    env.filters["regex_search"] = regex_search
    return env


def _manifest(root: Path) -> dict[str, dict]:
    """home.toml: path under home/ -> {mode: int, when: str}, checked."""
    layout = Layout(root)
    path = layout.home_toml
    if not path.exists():
        return {}
    entries = config.load(path, root)
    for rel, entry in entries.items():
        where = f"home.toml: {rel}"
        if not isinstance(entry, dict) or set(entry) - {"mode", "when"}:
            raise ConfigError(f"{where}: only mode and when are allowed")
        home = layout.home
        if not ((home / rel).exists() or (home / (rel + _SUFFIX)).exists()):
            raise ConfigError(f"{where}: no such file or directory under home/")
        if "mode" in entry:
            mode = entry["mode"]
            if not isinstance(mode, str) or len(mode) != 3 or set(mode) - set("01234567"):
                raise ConfigError(f'{where}: mode must be three octal digits, like "600"')
            entry["mode"] = int(mode, 8)
        if not isinstance(entry.get("when", ""), str):
            raise ConfigError(f"{where}: when must be a string")
    return entries


def template(dst: str, root: Path = Layout.root, **context) -> str:
    """system/DST.j2 rendered with CONTEXT: the content a feature writes to DST."""
    name = dst.lstrip("/") + _SUFFIX
    try:
        return _environment(Layout(root).system).get_template(name).render(context)
    except (jinja2.TemplateError, _TemplateFail) as e:
        raise _error(e, name, "", "system") from None


def _error(e: Exception, template: str, host: str, tree: str = "home") -> ConfigError:
    """The template's name and line, and the host, for any error raised while rendering."""
    line = getattr(e, "lineno", None)
    for frame in traceback.extract_tb(e.__traceback__):
        if frame.filename.endswith(template):
            line = frame.lineno
    where = f"{tree}/{template}" + (f":{line}" if line else "")
    host = f" {host}:" if host else ""
    return ConfigError(f"{where}:{host} {getattr(e, 'message', None) or e}")


def render(
    host: str,
    out: Path,
    root: Path = Layout.root,
    current: Path | None = None,
    cfg: dict | None = None,
) -> list[str]:
    """HOST's home tree rendered into the empty OUT; the paths written."""
    if out.exists() and any(out.iterdir()):
        raise ConfigError(f"{out}: not empty")
    home = Layout(root).home
    if not home.is_dir():
        return []
    entries = _manifest(root)
    env = _environment(home)
    cfg = config.resolve(host, root) if cfg is None else cfg
    # Plain dicts, so Jinja's errors say "dict object".
    plain = cfg.plain() if isinstance(cfg, config.Settings) else cfg
    context = plain | {"host": host, "home": str(Path.home()), "uid": os.getuid()}

    def enabled(rel: Path) -> bool:
        # A gate on a directory covers everything under it.
        """Whether the `when` of REL and of every directory above it holds."""
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
        is_template = src.is_file() and src.name.endswith(_SUFFIX)
        rel = src.relative_to(home)
        if is_template:
            rel = rel.with_name(rel.name.removesuffix(_SUFFIX))
        if not enabled(rel):
            continue
        dst = out / rel
        mode = entries.get(rel.as_posix(), {}).get("mode", _DEFAULT_MODE[src.is_dir()])
        if src.is_dir():
            dst.mkdir(exist_ok=True)
        elif is_template:
            name = src.relative_to(home).as_posix()
            cur = current / rel if current else None
            try:
                text = env.get_template(name).render(
                    context, current=cur.read_text() if cur and cur.is_file() else ""
                )
            except (jinja2.TemplateError, _TemplateFail) as e:
                raise _error(e, name, host) from None
            dst.write_text(text)
        else:
            shutil.copyfile(src, dst)
        dst.chmod(mode)
        written.append(rel.as_posix())
    return written


def _mode(path: Path) -> int:
    """PATH's permission bits."""
    return stat.S_IMODE(path.stat().st_mode)


def deploy(
    host: str,
    root: Path = Layout.root,
    home: Path | None = None,
    dry_run: bool = False,
    cfg: dict | None = None,
) -> list[str]:
    """HOST's dotfiles into HOME where they differ; one line per change."""
    home = home or Path.home()
    real_home = home.resolve()
    entries = _manifest(root)
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
                why = engine.differs(dst, content, want)
                if why is None:
                    continue
                if not dry_run:
                    fd, part = tempfile.mkstemp(dir=dst.parent, prefix=f".{dst.name}.")
                    with os.fdopen(fd, "wb") as f:
                        f.write(content)
                    os.chmod(part, want)
                    os.replace(part, dst)
            changes.append(f"-> ~/{rel} ({why})")
    return changes
