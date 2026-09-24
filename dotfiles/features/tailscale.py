"""The applying user as tailscale's operator, so tailscale up and status
need no sudo afterwards."""

import json
import os
import pwd

from dotfiles.engine import as_root, changed, output, run
from dotfiles.feature import Feature


class Tailscale(Feature):
    def apply(self, strategy):
        strategy.ensure_service("tailscaled.service")
        user = pwd.getpwuid(os.geteuid()).pw_name
        # Answers from the local socket, before an operator is set too.
        try:
            operator = json.loads(output("tailscale", "debug", "prefs") or "{}").get("OperatorUser")
        except json.JSONDecodeError:
            operator = None
        if operator == user:
            return
        with as_root():
            run("tailscale", "set", f"--operator={user}")
        changed(f"tailscale operator = {user}")

    class Arch:
        def packages(self):
            return ["tailscale"]
