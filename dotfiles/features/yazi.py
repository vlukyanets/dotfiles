from dotfiles.feature import Feature


class Yazi(Feature):
    class Arch:
        def packages(self):
            return ["yazi"]
