"""Not a feature of the schema: switched by ssh.generate_key. An ed25519 key
for this machine; the key never leaves ~/.ssh, only its .pub is worth
copying into data/ssh-pubkeys-collection.toml."""

import os
import pwd
import socket
import sys
from pathlib import Path

from dotfiles import engine
from dotfiles.engine import changed, notice, run
from dotfiles.feature import Feature


class SshKey(Feature):
    def apply(self, strategy):
        ssh = self.cfg["ssh"]
        key = Path.home() / ".ssh/id_ed25519"
        if not ssh["generate_key"] or key.exists():
            return
        if ssh["passphrase"] and not sys.stdin.isatty():
            notice(f"no SSH key at {key} and no terminal to ask for a passphrase — run: "
                   f"ssh-keygen -t ed25519 -f {key}")  # fmt: skip
            return
        # With a passphrase, ssh-keygen asks for it itself; without, the key has none.
        quiet = [] if ssh["passphrase"] else ["-q", "-N", ""]
        comment = f"{pwd.getpwuid(os.geteuid()).pw_name}@{socket.gethostname()}"
        if not engine.DRY_RUN:
            key.parent.mkdir(mode=0o700, exist_ok=True)
        run("ssh-keygen", "-t", "ed25519", *quiet, "-f", str(key), "-C", comment)
        changed(f"generated {key}")
        pub = key.with_name("id_ed25519.pub")
        notice(
            "new SSH public key — add it to data/ssh-pubkeys-collection.toml and wherever "
            "it should log in:\n" + (pub.read_text().strip() if pub.exists() else str(pub))
        )

    class Arch:
        def packages(self):
            return ["openssh"] if self.cfg["ssh"]["generate_key"] else []
