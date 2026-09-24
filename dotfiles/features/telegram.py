from dotfiles.feature import Feature


class Telegram(Feature):
    class Arch:
        def packages(self):
            return ["telegram-desktop"]
