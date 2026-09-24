from dotfiles.feature import Feature


class Evince(Feature):
    class Arch:
        def packages(self):
            return ["evince"]
