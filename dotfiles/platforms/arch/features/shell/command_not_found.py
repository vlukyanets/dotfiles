"""command-not-found on Arch: the shell names the package of a command it does not find, from pkgfile."""

import re
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template

_ZSH_HOOK = "~/.config/zsh/dotfiles.d/command-not-found.zsh"
_BASHRC = "~/.bashrc"
_BASH_HOOK = "source /usr/share/doc/pkgfile/command-not-found.bash"


class CommandNotFound(Feature):
    """pkgfile's handler for each of `shells`: zsh's through its snippet, bash's from ~/.bashrc."""

    rules: ClassVar[dict[str, tuple]] = {
        "shells": (
            lambda v: v and set(v) <= {"zsh", "bash"} and len(set(v)) == len(v),
            "zsh, bash or both, each once",
        ),
    }

    def requires(self) -> list[str]:
        """pkgfile: its database and handlers; zsh, for zsh: the snippet that loads the hook."""
        return [
            "package_tools.pkgfile",
            *(["shell.zsh"] if "zsh" in self.settings["shells"] else []),
        ]

    def apply(self) -> None:
        """The hook of each shell: zsh's file in dotfiles.d, bash's line at the end of ~/.bashrc."""
        files, home = self.system.files, Path.home()
        shells = self.settings["shells"]
        if "zsh" in shells:
            files.ensure(home / _ZSH_HOOK.removeprefix("~/"), template(_ZSH_HOOK))
        if "bash" in shells:
            # At the end: what bash reads before it stays the user's. ~/.bashrc has no
            # dotfiles.d of ours to drop a file into, as zsh's snippet has.
            files.line(home / _BASHRC.removeprefix("~/"), f"^{re.escape(_BASH_HOOK)}$", _BASH_HOOK)
