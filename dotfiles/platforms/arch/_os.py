"""Arch Linux: packages through pacman, from the repositories."""

from dotfiles.platforms.arch._pacman import Pacman
from dotfiles.platforms.linux import LinuxOs


class ArchLinuxOs(LinuxOs):
    """Arch Linux: packages through pacman, from the repositories."""

    id = "arch"
    manager_class = Pacman
