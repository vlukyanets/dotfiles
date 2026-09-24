"""Locales, LANG, the console keymap and font, the timezone. locale-gen,
the console setup and hwclock run only when their input changed."""

import re
import subprocess

from dotfiles import engine
from dotfiles.engine import as_root, ensure_file, ensure_line, ensure_symlink, notice, run
from dotfiles.feature import Feature

ROOT = "root:root"


class Locale(Feature):
    def apply(self, strategy):
        locale = self.cfg["features"]["locale"]
        # A list, not any(generator): every line is ensured, not just up to the first change.
        edits = [
            ensure_line("/etc/locale.gen", rf"^#?\s*{re.escape(line)}\s*$", line)
            for line in locale["locales"]
        ]
        if any(edits):
            with as_root():
                run("locale-gen", stdout=subprocess.DEVNULL)
        ensure_file("/etc/locale.conf", f"LANG={locale['lang']}\n", owner=ROOT)

        font = locale["console"]["font"]
        vconsole = f"KEYMAP={locale['keymap']}\n" + (f"FONT={font}\n" if font else "")
        if ensure_file("/etc/vconsole.conf", vconsole, owner=ROOT):
            fonts = engine.path("/usr/share/kbd/consolefonts")
            if font and not any(fonts.glob(f"{font}.psf*.gz")):
                notice(
                    f"console font {font} is not in /usr/share/kbd/consolefonts — the TTY "
                    "falls back to the kernel font; check features.locale.console.packages"
                )
            try:
                with as_root():
                    run("systemctl", "restart", "systemd-vconsole-setup.service")
            except subprocess.CalledProcessError:
                pass  # no console to set up, e.g. inside a graphical session
            if font and {"sd-vconsole", "consolefont"} & set(strategy.initramfs_hooks()):
                notice("console font changed — run 'sudo mkinitcpio -P' so early boot uses it too")

        zone = f"/usr/share/zoneinfo/{locale['timezone']}"
        if ensure_symlink(zone, "/etc/localtime"):
            with as_root():
                run("hwclock", "--systohc")

    class Arch:
        def packages(self):
            return list(self.cfg["features"]["locale"]["console"]["packages"])
