from dotfiles.engine import die
from dotfiles.feature import Feature


class Gaming(Feature):
    def apply(self, strategy):
        if not strategy.multilib():
            die("steam comes from [multilib] — set features.pacman.multilib = true")

    class Arch:
        def packages(self):
            if not self.multilib():
                return []  # nothing half-installed; apply says why
            return ["steam", "gamemode", "mangohud", "lib32-mangohud", "ttf-liberation"]
