from dotfiles.feature import Feature


class ObsStudio(Feature):
    class Arch:
        def packages(self):
            return ["obs-studio", "pipewire-jack"]

        def replaces(self):
            return ["jack2"]  # conflicts with pipewire-jack
