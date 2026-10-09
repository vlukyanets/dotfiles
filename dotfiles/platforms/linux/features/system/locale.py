"""locale on every Linux: locales generated, LANG, the console's keymap and font, the timezone."""

import re
import subprocess
from typing import ClassVar

from dotfiles.engine import die
from dotfiles.feature import Feature
from dotfiles.render import template

_LOCALE_GEN = "/etc/locale.gen"
_VCONSOLE = "/etc/vconsole.conf"
_FONTS = "/usr/share/kbd/consolefonts"
_ZONEINFO = "/usr/share/zoneinfo"


class Locale(Feature):
    """The locales generated, LANG and the console set, /etc/localtime the timezone."""

    rules: ClassVar[dict[str, tuple]] = {
        "timezone": (
            lambda v: re.fullmatch(r"[\w+-]+(/[\w+-]+)*", v),
            'a name like "Europe/Kyiv", a file under /usr/share/zoneinfo',
        ),
    }
    # Where LANG goes: systemd's file, read at login.
    locale_conf: ClassVar[str] = "/etc/locale.conf"

    def packages(self) -> list[str]:
        """What ships the console font."""
        return list(self.settings["console"]["packages"])

    def apply(self) -> None:
        """Every part, the timezone checked first: an unknown one changes nothing."""
        system, settings = self.system, self.settings
        zone = f"{_ZONEINFO}/{settings['timezone']}"
        if not system.files.path(zone).is_file():
            die(f"{settings['timezone']}: no such timezone in {_ZONEINFO}")
        self._generate()
        system.files.ensure(
            self.locale_conf, template(self.locale_conf, lang=settings["lang"]), owner="root:root"
        )
        self.console()
        system.files.symlink(zone, "/etc/localtime")

    def _generate(self) -> None:
        """Each line of `locales` uncommented in /etc/locale.gen, or added; locale-gen if one was."""
        files, shell = self.system.files, self.system.shell
        # A list, not any(generator): every line is ensured, not just up to the first change.
        edits = [
            files.line(_LOCALE_GEN, rf"^#?\s*{re.escape(line)}\s*$", line)
            for line in self.settings["locales"]
        ]
        if any(edits):
            with shell.as_root():
                shell.run("locale-gen", stdout=subprocess.DEVNULL)

    def console(self) -> None:
        """/etc/vconsole.conf, and the console set up again when it changed."""
        system, console = self.system, self.settings["console"]
        if not system.files.ensure(
            _VCONSOLE, template(_VCONSOLE, console=console), owner="root:root"
        ):
            return
        font = console["font"]
        if font and not any(system.files.path(_FONTS).glob(f"{font}.*")):
            system.report.notice(
                f"console font {font} is not in {_FONTS}: the console keeps the kernel's;"
                " check features.system.locale.console.packages"
            )
        try:
            with system.shell.as_root():
                system.shell.run("systemctl", "restart", "systemd-vconsole-setup.service")
        except subprocess.CalledProcessError:
            pass  # no console to set up: a container, or a VM without one
