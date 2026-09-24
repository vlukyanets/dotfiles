from dotfiles.feature import Feature


class Htop(Feature):
    class Arch:
        def packages(self):
            return ["htop"]
