import grp
import os
import pwd
import re
from contextlib import nullcontext

from dotfiles import engine
from dotfiles.engine import as_root, changed, die, ensure_line, notice, output, run
from dotfiles.platforms.operating_system import Platform


class Linux(Platform):
    """What every Linux has: systemd, sysctl, gsettings, groups; no package manager of its own."""

    def ensure_service(self, unit: str, user: bool = False) -> bool:
        """UNIT enabled and running, system-wide or USER's; whether it changed."""
        scope = ["--user"] if user else []
        enabled = output("systemctl", *scope, "is-enabled", unit) or ""
        active = output("systemctl", *scope, "is-active", unit) or ""
        if enabled in ("enabled", "static", "alias", "indirect"):
            if active == "active":
                return False
            verb = ["start"]
        else:
            verb = ["enable", "--now"]
        with nullcontext() if user else as_root():
            run("systemctl", *scope, *verb, unit)
        changed(f"{unit} enabled and started (was {enabled}/{active})")
        return True

    def ensure_sysctl(self, key: str, value) -> bool:
        """KEY = VALUE persisted in /etc/sysctl.d and live."""
        edited = ensure_line(
            "/etc/sysctl.d/99-dotfiles.conf", f"^{re.escape(key)} *=", f"{key} = {value}"
        )
        if output("sysctl", "-n", key) == str(value):
            return edited
        with as_root():
            run("sysctl", "-qw", f"{key}={value}")
        changed(f"sysctl {key} = {value}")
        return True

    def ensure_gsetting(self, schema: str, key: str, value: str) -> bool:
        """SCHEMA KEY is VALUE; nothing where gsettings is missing."""
        current = output("gsettings", "get", schema, key)
        if current is None or current == value:
            return False
        run("gsettings", "set", schema, key, value)
        changed(f"gsettings {schema} {key} = {value}")
        return True

    def ensure_group_member(self, group: str) -> bool:
        """This user in GROUP; a notice to log in again when added."""
        me = pwd.getpwuid(os.geteuid())
        try:
            entry = grp.getgrnam(group)
        except KeyError:
            if not engine.current().dry_run:
                die(f"group {group} does not exist")
            entry = None  # its package, not installed by a dry run, brings it
        if entry and (me.pw_name in entry.gr_mem or me.pw_gid == entry.gr_gid):
            return False
        with as_root():
            run("usermod", "-aG", group, me.pw_name)
        changed(f"added {me.pw_name} to group {group}")
        notice(f"added to group {group} — log out and back in for it to take effect")
        return True
