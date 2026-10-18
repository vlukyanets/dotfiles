"""Templates: host files ending in .tmpl, filled when they are installed.

A placeholder is `{{ name }}`, name in [a-z0-9_]; the rest of a template is
kept as it is. The values live outside the repository, in
~/.config/dotfiles/<host>.toml (under $XDG_CONFIG_HOME when it is set), a
flat TOML table of strings, closed to others. A value is never printed.
"""

import getpass
import os
import re
import sys
import tomllib
from pathlib import Path

from dotfiles.machine import Error

SUFFIX = ".tmpl"
PLACEHOLDER = re.compile(r"\{\{ *([a-z0-9_]+) *\}\}")


def values_path(host: str) -> Path:
    config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(config) / "dotfiles" / f"{host}.toml"


def read_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        table = tomllib.loads(path.read_text())
    except tomllib.TOMLDecodeError as e:
        raise Error(f"{path}: {e}") from None  # Its message names a place, not a value.
    for name, value in table.items():
        if not isinstance(value, str):
            raise Error(f"{path}: {name} is not a string")
    return table


def toml_string(value: str) -> str:
    """value as a TOML basic string."""
    return '"' + "".join(
        c if " " <= c != "\x7f" and c not in '"\\' else f"\\u{ord(c):04x}" for c in value
    ) + '"'


def save_value(path: Path, name: str, value: str) -> None:
    """Adds name to the values file, creating it closed to others."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as f:
        f.write(f"{name} = {toml_string(value)}\n")


def text_of(path: Path) -> str:
    try:
        return path.read_bytes().decode()
    except UnicodeDecodeError:
        raise Error(f"a template must be UTF-8 text: {path}") from None


def names(text: str) -> list[str]:
    """The placeholders of a template, each once, in order."""
    return list(dict.fromkeys(PLACEHOLDER.findall(text)))


def fill(text: str, values: dict[str, str]) -> str:
    return PLACEHOLDER.sub(lambda m: values[m[1]], text)


def values_for(host_dir: Path, ask: bool) -> dict[str, str]:
    """The values of host_dir's templates. With ask, a missing one is asked
    for, without echo, and saved; without, it stays missing."""
    path = values_path(host_dir.name)
    values = read_values(path)
    needed = [name for template in sorted(host_dir.rglob(f"*{SUFFIX}")) if template.is_file()
              for name in names(text_of(template))]
    for name in dict.fromkeys(needed):
        if name in values or not ask:
            continue
        if not sys.stdin.isatty():
            raise Error(f"no value for {name} in {path}")
        values[name] = getpass.getpass(f"value for {name}: ")
        save_value(path, name, values[name])
    return values
