from dotfiles.feature import Feature


class Noctalia(Feature):
    class Arch:
        def packages(self):
            return ["noctalia"]
