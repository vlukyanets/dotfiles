from dotfiles.feature import Feature


class Mtr(Feature):
    class Arch:
        def packages(self):
            return ["mtr"]
