from dotfiles.feature import Feature


class Loupe(Feature):
    class Arch:
        def packages(self):
            return ["loupe"]
