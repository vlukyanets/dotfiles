"""timesyncd on every Linux: the clock kept in sync by systemd-timesyncd."""

from dotfiles.feature import Feature


class Timesyncd(Feature):
    """systemd-timesyncd.service enabled and running; part of systemd, no packages."""

    def apply(self) -> None:
        """The service on."""
        self.system.ensure_service("systemd-timesyncd.service")
