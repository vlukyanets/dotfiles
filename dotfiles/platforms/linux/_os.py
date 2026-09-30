"""Linux: what every distribution shares, and the base the platforms fall back to."""

import grp
import os
import pwd
import re
from contextlib import nullcontext

from dotfiles.engine import die
from dotfiles.platforms.operating_system import OperatingSystem


class LinuxOs(OperatingSystem):
    """What every Linux has: systemd, sysctl, gsettings, groups; no package manager of its own."""

    def ensure_service(self, unit: str, user: bool = False) -> bool:
        """UNIT enabled and running, system-wide or USER's; whether it changed."""
        scope = ["--user"] if user else []
        enabled = self.shell.output("systemctl", *scope, "is-enabled", unit) or ""
        active = self.shell.output("systemctl", *scope, "is-active", unit) or ""
        if enabled in ("enabled", "static", "alias", "indirect"):
            if active == "active":
                return False
            verb = ["start"]
        else:
            verb = ["enable", "--now"]
        with nullcontext() if user else self.shell.as_root():
            self.shell.run("systemctl", *scope, *verb, unit)
        self.report.changed(f"{unit} enabled and started (was {enabled}/{active})")
        return True

    def ensure_sysctl(self, key: str, value) -> bool:
        """KEY = VALUE persisted in /etc/sysctl.d and live."""
        edited = self.files.line(
            "/etc/sysctl.d/99-dotfiles.conf", f"^{re.escape(key)} *=", f"{key} = {value}"
        )
        if self.shell.output("sysctl", "-n", key) == str(value):
            return edited
        with self.shell.as_root():
            self.shell.run("sysctl", "-qw", f"{key}={value}")
        self.report.changed(f"sysctl {key} = {value}")
        return True

    def ensure_gsetting(self, schema: str, key: str, value: str) -> bool:
        """SCHEMA KEY is VALUE; nothing where gsettings is missing."""
        current = self.shell.output("gsettings", "get", schema, key)
        if current is None or current == value:
            return False
        self.shell.run("gsettings", "set", schema, key, value)
        self.report.changed(f"gsettings {schema} {key} = {value}")
        return True

    def ensure_group_member(self, group: str) -> bool:
        """This user in GROUP; a notice to log in again when added."""
        me = pwd.getpwuid(os.geteuid())
        try:
            entry = grp.getgrnam(group)
        except KeyError:
            die(f"group {group} does not exist")
        if me.pw_name in entry.gr_mem or me.pw_gid == entry.gr_gid:
            return False
        with self.shell.as_root():
            self.shell.run("usermod", "-aG", group, me.pw_name)
        self.report.changed(f"added {me.pw_name} to group {group}")
        self.report.notice(f"added to group {group} — log out and back in for it to take effect")
        return True
