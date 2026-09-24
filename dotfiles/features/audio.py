from dotfiles.feature import Feature


class Audio(Feature):
    class Arch:
        def packages(self):
            return [
                "pipewire-pulse",
                "pipewire-alsa",
                "pipewire-jack",
                "wireplumber",
                "playerctl",
                "brightnessctl",
            ]

        def replaces(self):
            return ["jack2"]  # conflicts with pipewire-jack
