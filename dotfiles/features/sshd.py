"""The OpenSSH server with a hardening drop-in, reloaded only when the
drop-in changed and the daemon runs."""

from dotfiles import engine
from dotfiles.engine import as_root, ensure_file, notice, output, run
from dotfiles.feature import Feature

CONF = "/etc/ssh/sshd_config.d/dotfiles.conf"


class Sshd(Feature):
    def apply(self, strategy):
        sshd = self.cfg["features"]["sshd"]
        password = "yes" if sshd["password_auth"] else "no"
        conf = f"PasswordAuthentication {password}\nPermitRootLogin {sshd['permit_root_login']}\n"
        real = engine.path(CONF)
        was = real.read_text().splitlines() if real.exists() else []
        if password == "no" and "PasswordAuthentication no" not in was:
            notice(
                "sshd: password login is being turned off — make sure a key login works "
                "before closing this session"
            )
        if (
            ensure_file(CONF, conf, owner="root:root")
            and output("systemctl", "is-active", "sshd.service") == "active"
        ):
            with as_root():
                run("systemctl", "reload", "sshd.service")
        strategy.ensure_service("sshd.service")

    class Arch:
        def packages(self):
            return ["openssh"]
