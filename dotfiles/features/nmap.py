from dotfiles.feature import Feature


class Nmap(Feature):
    class Arch:
        def packages(self):
            return ["nmap"]
