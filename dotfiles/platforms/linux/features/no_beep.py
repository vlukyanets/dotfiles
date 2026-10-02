"""no_beep on Linux: the PC speaker's drivers blacklisted, and unloaded if loaded."""

import subprocess

from dotfiles.feature import Feature
from dotfiles.render import template

_CONF = "/etc/modprobe.d/nobeep.conf"
_MODULES = ("pcspkr", "snd_pcsp")  # the console's beeper; ALSA's driver of the same speaker


class NoBeep(Feature):
    """The PC speaker silent: never loaded at boot, and unloaded now."""

    def apply(self) -> None:
        """The blacklist written; the loaded drivers unloaded, or a reboot asked for."""
        system = self.system
        system.files.ensure(_CONF, template(_CONF), owner="root:root")
        if not (loaded := [m for m in _MODULES if system.files.path(f"/sys/module/{m}").is_dir()]):
            return
        try:
            with system.shell.as_root():
                system.shell.run("modprobe", "-r", *loaded)
        except subprocess.CalledProcessError:  # snd_pcsp held by a sound server
            system.report.notice(
                f"{' '.join(loaded)} in use: the PC speaker is silent after a reboot"
            )
            return
        system.report.changed(f"{' '.join(loaded)} unloaded")
