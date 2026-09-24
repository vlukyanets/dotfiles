from dotfiles.feature import Feature


class Kitty(Feature):
    class Arch:
        def packages(self):
            return ["kitty"]
