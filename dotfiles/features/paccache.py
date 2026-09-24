from dotfiles.feature import Feature


class Paccache(Feature):
    def apply(self, strategy):
        strategy.ensure_service("paccache.timer")

    class Arch:
        def packages(self):
            return ["pacman-contrib"]
