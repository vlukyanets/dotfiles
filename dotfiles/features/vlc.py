from dotfiles.feature import Feature


class Vlc(Feature):
    class Arch:
        def packages(self):
            return ["vlc"]
