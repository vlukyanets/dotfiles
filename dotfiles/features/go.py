from dotfiles.feature import Feature


class Go(Feature):
    class Arch:
        def packages(self):
            return ["go", "delve"]
