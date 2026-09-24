from dotfiles.feature import Feature


class Fwupd(Feature):
    def apply(self, strategy):
        strategy.ensure_service("fwupd-refresh.timer")

    class Arch:
        def packages(self):
            return ["fwupd"]
