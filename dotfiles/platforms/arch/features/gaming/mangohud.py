"""MangoHud on Arch: the overlay a game gets through `mangohud %command%`."""

from dotfiles.feature import Feature, Setting


class Mangohud(Feature):
    """mangohud for 64- and 32-bit games; its config stays the user's."""

    def packages(self) -> list[str]:
        """mangohud and lib32-mangohud, of [multilib]."""
        return ["mangohud", "lib32-mangohud"]

    def requires(self) -> list[str | Setting]:
        """multilib, for lib32-mangohud."""
        return [Setting("packaging.pacman.multilib", True)]
