from dotfiles.feature import Feature


class Jdk(Feature):
    class Arch:
        def packages(self):
            return ["jdk-openjdk"]
