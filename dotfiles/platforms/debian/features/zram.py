"""zram on Debian: Linux's, from Debian's package of the generator."""

from dotfiles.platforms.linux.features import zram


class Zram(zram.Zram):
    """Linux's zram; Debian names the generator's package after systemd."""

    def packages(self) -> list[str]:
        """zram-generator, as Debian names it."""
        return ["systemd-zram-generator"]
