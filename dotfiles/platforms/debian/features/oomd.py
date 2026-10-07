"""oomd on Debian: Linux's, from its own package."""

from dotfiles.platforms.linux.features import oomd


class Oomd(oomd.Oomd):
    """Linux's oomd; Debian ships it apart from systemd."""

    def packages(self) -> list[str]:
        """systemd-oomd."""
        return ["systemd-oomd"]
