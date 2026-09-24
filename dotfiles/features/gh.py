from dotfiles.feature import Feature


class Gh(Feature):
    class Arch:
        def packages(self):
            return ["github-cli"]
