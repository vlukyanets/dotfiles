from dotfiles.feature import Feature


class Sccache(Feature):
    class Arch:
        def packages(self):
            return ["sccache"]
