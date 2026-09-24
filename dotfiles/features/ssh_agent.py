"""openssh's ssh-agent.socket, a user unit. SSH_AUTH_SOCK reaches the
session through ~/.config/environment.d and .zshrc, both read at login."""

from dotfiles.engine import notice, output
from dotfiles.feature import Feature


class SshAgent(Feature):
    def apply(self, strategy):
        if not output("systemctl", "--user", "show-environment"):
            notice(
                "no systemd user session here — run once from a login session: "
                "systemctl --user enable --now ssh-agent.socket"
            )
            return
        if strategy.ensure_service("ssh-agent.socket", user=True):
            notice("ssh-agent enabled — log out and back in so the session picks up SSH_AUTH_SOCK")

    class Arch:
        def packages(self):
            return ["openssh"]
