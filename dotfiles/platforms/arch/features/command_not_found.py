"""command-not-found on Arch: zsh names the package of a command it does not find, from pkgfile."""

from pathlib import Path

from dotfiles.feature import Feature
from dotfiles.render import template

_HOOK = "~/.config/zsh/dotfiles.d/command-not-found.zsh"


class CommandNotFound(Feature):
    """pkgfile's handler loaded by zsh's snippet, which sources every file of dotfiles.d."""

    def requires(self) -> list[str]:
        """pkgfile: its database and handler; zsh: the snippet that loads the hook."""
        return ["pkgfile", "zsh"]

    def apply(self) -> None:
        """The hook written."""
        self.system.files.ensure(Path.home() / _HOOK.removeprefix("~/"), template(_HOOK))
