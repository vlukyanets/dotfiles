from dotfiles.feature import Feature


class Android(Feature):
    def apply(self, strategy):
        strategy.ensure_group_member("adbusers")

    class Arch:
        def packages(self):
            return ["android-tools", "android-udev"]
