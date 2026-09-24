from dotfiles.feature import Feature


class Termusic(Feature):
    class Arch:
        def packages(self):
            return ["termusic"]
