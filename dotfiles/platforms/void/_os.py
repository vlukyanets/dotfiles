"""Void Linux: packages through xbps, from the repositories."""

from dotfiles.engine import die
from dotfiles.platforms.linux import LinuxOs
from dotfiles.platforms.void._xbps import Xbps


class VoidOs(LinuxOs):
    """Void Linux: packages through xbps; runit, not systemd."""

    id = "void"
    manager_class = Xbps

    def ensure_service(self, unit: str, user: bool = False) -> bool:
        """None: a feature that needs a service has no Void module yet."""
        die(f"{unit}: Void has runit, not systemd")
