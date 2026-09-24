from dotfiles.feature import Feature


class Timesyncd(Feature):
    def apply(self, strategy):
        strategy.ensure_service("systemd-timesyncd.service")

    class Linux:
        """Part of systemd: no packages."""
