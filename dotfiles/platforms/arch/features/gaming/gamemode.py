"""GameMode on Arch: the daemon games ask for performance, and its group."""

from dotfiles.feature import Feature, Setting


class Gamemode(Feature):
    """gamemode for 64- and 32-bit games, this user in its group."""

    def packages(self) -> list[str]:
        """gamemode and lib32-gamemode, of [multilib]."""
        return ["gamemode", "lib32-gamemode"]

    def requires(self) -> list[str | Setting]:
        """multilib, for lib32-gamemode."""
        return [Setting("packaging.pacman.multilib", True)]

    def apply(self) -> None:
        """This user in gamemode: its limits.d lets the group renice games."""
        self.system.ensure_group_member("gamemode")
