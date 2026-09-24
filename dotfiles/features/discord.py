from dotfiles.feature import Feature


class Discord(Feature):
    class Arch:
        def packages(self):
            return ["discord"]
