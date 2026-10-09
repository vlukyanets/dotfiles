"""zsh on Debian: Linux's, with the extras where Debian puts them."""

from typing import ClassVar

from dotfiles.platforms.linux.features.shell import zsh


class Zsh(zsh.Zsh):
    """Linux's zsh; Debian puts an extra in /usr/share/<extra>, and has no zsh-completions."""

    extras_dir: ClassVar[str] = "/usr/share"
