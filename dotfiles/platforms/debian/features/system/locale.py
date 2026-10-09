"""locale on Debian: Linux's, with LANG where Debian reads it and no console of ours."""

from typing import ClassVar

from dotfiles.platforms.linux.features.system import locale


class Locale(locale.Locale):
    """Linux's locale; Debian's console-setup reads its own files, not /etc/vconsole.conf."""

    locale_conf: ClassVar[str] = "/etc/default/locale"

    def packages(self) -> list[str]:
        """locale-gen and /etc/locale.gen: not in a minimal install."""
        return ["locales"]

    def console(self) -> None:
        """Nothing written; a notice when a host asks for more than Debian's own console."""
        console = self.settings["console"]
        if console["keymap"] != "us" or console["font"]:  # "us": the schema's default and Debian's
            self.system.report.notice(
                "features.system.locale.console is not applied on Debian: set it with"
                " `dpkg-reconfigure keyboard-configuration console-setup`"
            )
