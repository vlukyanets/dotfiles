from dotfiles.feature import Feature


class Onlyoffice(Feature):
    class Arch:
        def packages(self):
            return ["onlyoffice-bin"]
