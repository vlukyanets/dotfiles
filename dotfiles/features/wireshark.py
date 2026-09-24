from dotfiles.feature import Feature


class Wireshark(Feature):
    def apply(self, strategy):
        strategy.ensure_group_member("wireshark")

    class Arch:
        def packages(self):
            return ["wireshark-qt", "qt6-multimedia-ffmpeg"]
