from dotfiles.feature import Feature


class Btop(Feature):
    class Arch:
        def packages(self):
            return ["btop"]
