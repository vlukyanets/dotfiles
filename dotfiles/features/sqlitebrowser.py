from dotfiles.feature import Feature


class Sqlitebrowser(Feature):
    class Arch:
        def packages(self):
            return ["sqlitebrowser"]
