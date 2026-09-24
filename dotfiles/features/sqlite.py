from dotfiles.feature import Feature


class Sqlite(Feature):
    class Arch:
        def packages(self):
            return ["sqlite"]
