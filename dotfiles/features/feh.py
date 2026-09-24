from dotfiles.feature import Feature


class Feh(Feature):
    class Arch:
        def packages(self):
            return ["feh"]
