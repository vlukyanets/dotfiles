"""Where things are: in a dotfiles checkout, and this machine's own config."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from dotfiles.errors import ConfigError

# The checkout this code runs from.
_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Layout:
    """The paths of the checkout at ROOT; another checkout (--source, a test's) has the same."""

    root: Path = _ROOT

    # The schema: every key, its type and its default. Relative, as messages name it.
    DEFAULTS: ClassVar[str] = "dotfiles/defaults.toml"

    @property
    def defaults(self) -> Path:
        """The schema."""
        return self.root / self.DEFAULTS

    @property
    def hosts(self) -> Path:
        """One TOML file per machine."""
        return self.root / "hosts"

    @property
    def profiles(self) -> Path:
        """What machines extend; one namespace with hosts."""
        return self.root / "profiles"

    @property
    def system(self) -> Path:
        """Templates of the files features write, at their path from /."""
        return self.root / "system"

    @property
    def home(self) -> Path:
        """Templates of the files features write in $HOME, at their path from it."""
        return self.root / "home"

    def host_names(self) -> list[str]:
        """Every host by its path under hosts/, without .toml: `vm/dotfiles/node-arch`."""
        return sorted(
            p.relative_to(self.hosts).with_suffix("").as_posix() for p in self.hosts.rglob("*.toml")
        )

    def named(self, name: str) -> Path | None:
        """NAME's file, .toml optional: a path under hosts/ if it has a `/`, else the one
        host or profile of that name, in any folder under hosts/; None if there is none.
        """
        name = name.removesuffix(".toml")
        if "/" in name:
            path = self.hosts / f"{name}.toml"
            return path if path.is_file() else None
        # ponytail: rglob on every lookup; index once if hosts/ grows to thousands of files.
        found = sorted(self.profiles.glob(f"{name}.toml")) + sorted(
            self.hosts.rglob(f"{name}.toml")
        )
        if len(found) > 1:
            files = ", ".join(str(p.relative_to(self.root)) for p in found)
            raise ConfigError(f"ambiguous name {name!r}: {files}; give its path under hosts/")
        return found[0] if found else None


def local_config() -> Path:
    """This machine's config, written by `dotfiles init`."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "dotfiles" / "config.toml"


def shown(path: Path) -> str:
    """PATH with ~ for the home directory, the way errors and changes name it."""
    return f"~/{path.relative_to(Path.home())}" if path.is_relative_to(Path.home()) else str(path)
