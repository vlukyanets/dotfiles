from dotfiles.engine import die
from dotfiles.feature import Feature


def multilib(cfg: dict) -> bool:
    pacman = cfg["features"]["pacman"]
    return pacman["enabled"] and pacman["multilib"]


class Gaming(Feature):
    def apply(self, strategy):
        if not multilib(self.cfg):
            die("steam comes from [multilib] — set features.pacman.multilib = true")

    class Arch:
        def packages(self):
            if not multilib(self.cfg):
                return []  # nothing half-installed; apply says why
            return ["steam", "gamemode", "mangohud", "lib32-mangohud", "ttf-liberation"]
