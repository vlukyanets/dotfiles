from dotfiles.feature import Feature


class Fonts(Feature):
    class Arch:
        def packages(self):
            return ["noto-fonts-emoji", "noto-fonts-cjk"]
