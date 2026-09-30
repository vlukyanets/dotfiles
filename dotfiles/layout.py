"""Where things are: in a dotfiles checkout, and this machine's own config."""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

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
    def home(self) -> Path:
        """The dotfiles, at their path under $HOME."""
        return self.root / "home"

    @property
    def home_toml(self) -> Path:
        """Modes and gates of the paths under home/."""
        return self.root / "home.toml"

    @property
    def system(self) -> Path:
        """Templates of the files features write outside $HOME, at their path from /."""
        return self.root / "system"

    def host(self, name: str) -> Path:
        """Host NAME's file."""
        return self.hosts / f"{name}.toml"


def local_config() -> Path:
    """This machine's config, written by `dotfiles init`."""
    base = os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")
    return Path(base) / "dotfiles" / "config.toml"


def shown(path: Path) -> str:
    """PATH with ~ for the home directory, the way errors and changes name it."""
    return f"~/{path.relative_to(Path.home())}" if path.is_relative_to(Path.home()) else str(path)
