"""git on every Linux: the user's name and email in our file, included from the top of the config."""

import re
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template

_OURS = "~/.config/git/dotfiles.gitconfig"
_CONFIG = "~/.config/git/config"
# Relative to the config that includes it; [section] and key on one line are git's syntax too.
_INCLUDE = "[include] path = dotfiles.gitconfig"


class Git(Feature):
    """git, and user.name and user.email where set; the rest of the config stays the user's."""

    rules: ClassVar[dict[str, tuple]] = {
        "name": (lambda v: re.fullmatch(r'[^"\\\n]*', v), 'a name without " or \\'),
        "email": (lambda v: v == "" or re.fullmatch(r"[^\s@]+@[^\s@]+", v), "an email address"),
    }

    def packages(self) -> list[str]:
        """git itself."""
        return ["git"]

    def apply(self) -> None:
        """Our file written, and included at the top of ~/.config/git/config."""
        home, files = Path.home(), self.system.files
        files.ensure(home / _OURS.removeprefix("~/"), template(_OURS, git=self.settings))
        # At the top: the rest of the config, and ~/.gitconfig, stay the user's and override ours.
        files.line(
            home / _CONFIG.removeprefix("~/"), f"^{re.escape(_INCLUDE)}$", _INCLUDE, before="."
        )
