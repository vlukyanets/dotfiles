from dotfiles.feature import Feature


class Doublecmd(Feature):
    class Arch:
        def packages(self):
            return ["doublecmd-qt6"]
