"""A monthly scrub of the root btrfs."""

from dotfiles.feature import Feature


class BtrfsScrub(Feature):
    def apply(self, strategy):
        strategy.ensure_service("btrfs-scrub@-.timer")

    class Arch:
        def packages(self):
            return ["btrfs-progs"]
