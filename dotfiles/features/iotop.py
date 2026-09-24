from dotfiles.feature import Feature


class Iotop(Feature):
    class Arch:
        def packages(self):
            return ["iotop"]
