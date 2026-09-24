"""The Plymouth boot splash: its mkinitcpio hook and the bgrt theme. The
initramfs is rebuilt by plymouth-set-default-theme -R, only when the theme
or the hook changes."""

from dotfiles.engine import as_root, changed, die, ensure_line, notice, output, run
from dotfiles.feature import Feature


class Plymouth(Feature):
    def apply(self, strategy):
        hooks = strategy.initramfs_hooks()
        added = "plymouth" not in hooks
        if added:
            after = next((h for h in ("systemd", "udev", "base") if h in hooks), None)
            if after is None:
                die("no systemd, udev or base hook in /etc/mkinitcpio.conf to put plymouth after")
            hooks.insert(hooks.index(after) + 1, "plymouth")
            ensure_line("/etc/mkinitcpio.conf", r"^HOOKS=", f"HOOKS=({' '.join(hooks)})")
        if added or output("plymouth-set-default-theme") != "bgrt":
            with as_root():
                run("plymouth-set-default-theme", "-R", "bgrt")
            changed("plymouth theme bgrt, initramfs rebuilt")
            notice("plymouth: add 'quiet splash' to the kernel cmdline for the splash to show")

    class Arch:
        def packages(self):
            return ["plymouth"]
