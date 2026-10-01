"""reflector on Arch: the mirrorlist refreshed on a timer, and at once when a setting changes."""

import subprocess
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template

_CONF = "/etc/xdg/reflector/reflector.conf"
_TIMER_OVERRIDE = "/etc/systemd/system/reflector.timer.d/override.conf"

_PROTOCOLS = ("https", "http", "rsync", "ftp")
_SORTS = ("age", "rate", "country", "score", "delay")


class Reflector(Feature):
    """reflector installed, its config and timer written, the timer on."""

    rules: ClassVar[dict[str, tuple]] = {
        "protocol": (lambda v: v in _PROTOCOLS, f"one of {', '.join(_PROTOCOLS)}"),
        "sort": (lambda v: v in _SORTS, f"one of {', '.join(_SORTS)}"),
        "latest": (lambda v: v >= 1, "1 or more"),
        "age": (lambda v: v >= 1, "1 or more"),
        "completion_percent": (lambda v: 0 <= v <= 100, "0 to 100"),
        "download_timeout": (lambda v: v >= 1, "1 or more"),
        "on_calendar": (lambda v: v != "", "a calendar event, e.g. weekly"),
        "on_boot_sec": (lambda v: v != "", "a time span, e.g. 15min"),
    }

    def packages(self) -> list[str]:
        """reflector itself."""
        return ["reflector"]

    def apply(self) -> None:
        """The config and the timer override, the timer on; the mirrorlist refreshed if any changed."""
        system = self.system
        edited = system.files.ensure(
            _CONF, template(_CONF, reflector=self.settings), owner="root:root"
        )
        if system.files.ensure(
            _TIMER_OVERRIDE, template(_TIMER_OVERRIDE, reflector=self.settings), owner="root:root"
        ):
            with system.shell.as_root():
                system.shell.run("systemctl", "daemon-reload")
            edited = True
        edited = system.ensure_service("reflector.timer") or edited
        if not edited:
            return
        # Now, not at the timer's next run: the next install downloads from these mirrors.
        try:
            with system.shell.as_root():
                system.shell.run("systemctl", "start", "reflector.service")
        except subprocess.CalledProcessError:
            system.report.notice(
                "refreshing the mirrorlist failed (network?): the old one stays,"
                " reflector.timer tries again"
            )
            return
        system.report.changed("mirrorlist refreshed")
