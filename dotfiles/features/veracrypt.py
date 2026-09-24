from dotfiles.feature import Feature


class Veracrypt(Feature):
    class Arch:
        def packages(self):
            return ["veracrypt"]
