from dotfiles.feature import Feature


class Dig(Feature):
    class Arch:
        def packages(self):
            return ["bind"]
