from dotfiles.feature import Feature


class NerdFont(Feature):
    class Arch:
        def packages(self):
            return ["ttf-firacode-nerd", "ttf-nerd-fonts-symbols-mono"]
