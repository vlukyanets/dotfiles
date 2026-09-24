from dotfiles.feature import Feature


class Tcpdump(Feature):
    class Arch:
        def packages(self):
            return ["tcpdump"]
