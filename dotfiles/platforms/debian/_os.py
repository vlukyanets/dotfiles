"""Debian: packages through apt, from the repositories."""

from dotfiles.platforms.debian._apt import Apt
from dotfiles.platforms.linux import LinuxOs


class DebianOs(LinuxOs):
    """Debian: packages through apt, from the repositories."""

    id = "debian"
    manager_class = Apt
