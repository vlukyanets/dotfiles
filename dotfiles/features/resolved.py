"""DNS through systemd-resolved's stub, with NetworkManager handing its
servers over instead of writing resolv.conf itself."""

import subprocess

from dotfiles.engine import as_root, ensure_file, ensure_symlink, notice, output, run
from dotfiles.feature import Feature


class Resolved(Feature):
    def apply(self, strategy):
        strategy.ensure_service("systemd-resolved.service")
        ensure_symlink("/run/systemd/resolve/stub-resolv.conf", "/etc/resolv.conf")
        dns = "[main]\ndns=systemd-resolved\n"
        if not ensure_file("/etc/NetworkManager/conf.d/dns.conf", dns, owner="root:root"):
            return
        if output("systemctl", "is-active", "NetworkManager.service") != "active":
            return
        with as_root():
            run("systemctl", "restart", "NetworkManager.service")
        try:  # the check NetworkManager-wait-online makes, so later features get a network
            run("nm-online", "-s", "-q", "-t", "30")
        except subprocess.CalledProcessError:
            notice(
                "NetworkManager is still not up 30s after its restart — features that "
                "needed the network may have failed"
            )

    class Linux:
        """Part of systemd; NetworkManager is the host's own."""
