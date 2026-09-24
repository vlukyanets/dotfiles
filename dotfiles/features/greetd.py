"""greetd with the greeter of features.greetd."""

from dotfiles.engine import as_root, changed, die, ensure_file, notice, output, run
from dotfiles.feature import Feature

SESSIONS = "/usr/share/xsessions:/usr/share/wayland-sessions"
GREETERS = {"tuigreet": "greetd-tuigreet", "noctalia-greeter": "noctalia-greeter"}


class Greetd(Feature):
    def apply(self, strategy):
        greetd = self.cfg["features"]["greetd"]
        greeter = greetd["greeter"]
        if greeter == "tuigreet":
            command = f"tuigreet --remember --remember-session --sessions {SESSIONS}"
        elif greeter == "noctalia-greeter":
            # What follows "--" goes to noctalia-greeter itself; greetd knows no --session.
            extra = [*(["--session", greetd["session"]] if greetd["session"] else []),
                     *(["--user", greetd["user"]] if greetd["user"] else [])]  # fmt: skip
            command = " ".join(["noctalia-greeter-session", *(["--", *extra] if extra else [])])
        else:
            die(f"features.greetd.greeter {greeter!r}: tuigreet or noctalia-greeter")
        conf = f'[terminal]\nvt = 1\n\n[default_session]\ncommand = "{command}"\nuser = "greeter"\n'
        ensure_file("/etc/greetd/config.toml", conf, owner="root:root")
        # Enabled, not started: starting it would take over the VT this apply may run on.
        if output("systemctl", "is-enabled", "greetd.service") != "enabled":
            with as_root():
                run("systemctl", "enable", "greetd.service")
            changed("greetd.service enabled")
            notice("greetd is enabled — reboot to log in through the greeter")

    class Arch:
        def packages(self):
            greeter = GREETERS.get(self.cfg["features"]["greetd"]["greeter"])
            return ["greetd", greeter] if greeter else []  # an unknown one: apply says so
