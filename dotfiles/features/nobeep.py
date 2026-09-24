"""Silence the PC speaker."""

from dotfiles.engine import ensure_file
from dotfiles.feature import Feature


class Nobeep(Feature):
    def apply(self, strategy):
        ensure_file("/etc/modprobe.d/nobeep.conf", "blacklist pcspkr\n", owner="root:root")

    class Linux:
        """A kernel module: the same on every Linux, no packages."""
