"""timesyncd on Debian: Linux's, from its own package."""

from dotfiles.platforms.linux.features.system import timesyncd


class Timesyncd(timesyncd.Timesyncd):
    """Linux's timesyncd; Debian ships it apart from systemd."""

    def packages(self) -> list[str]:
        """systemd-timesyncd: apt removes another time daemon (chrony, ntpsec) for it."""
        return ["systemd-timesyncd"]
