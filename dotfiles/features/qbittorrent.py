from dotfiles.feature import Feature


class Qbittorrent(Feature):
    class Arch:
        def packages(self):
            return ["qbittorrent"]
