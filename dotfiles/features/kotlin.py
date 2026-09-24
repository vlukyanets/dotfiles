from dotfiles.feature import Feature


class Kotlin(Feature):
    class Arch:
        def packages(self):
            return ["kotlin", "gradle"]
