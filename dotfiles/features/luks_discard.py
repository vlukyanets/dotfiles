"""TRIM through dm-crypt: discard in the options of every LUKS volume the
kernel cmdline opens. The initramfs rebuild that makes it effective is
left to the user (a notice)."""

import re

from dotfiles import engine
from dotfiles.engine import ensure_line, notice
from dotfiles.feature import Feature

CMDLINE = "/etc/kernel/cmdline"


class LuksDiscard(Feature):
    def apply(self, strategy):
        if "sd-encrypt" not in strategy.initramfs_hooks():
            notice(
                "luks_discard: no sd-encrypt hook in /etc/mkinitcpio.conf — with the encrypt "
                "hook, add :allow-discards to cryptdevice= by hand"
            )
            return
        real = engine.path(CMDLINE)
        if not real.exists():
            notice(
                f"luks_discard: {CMDLINE} does not exist (no UKI?) — add "
                "rd.luks.options=<uuid>:discard to the boot loader entry by hand"
            )
            return
        line = real.read_text().split("\n", 1)[0]
        wanted = with_discard(line)
        if wanted is None:
            notice(f"luks_discard: no rd.luks.name= in {CMDLINE} — nothing to add discard to")
            return
        # The cmdline is one line: "^" matches it.
        if ensure_line(CMDLINE, "^", wanted):
            notice(
                f"LUKS discard enabled in {CMDLINE} — run 'sudo mkinitcpio -P' and reboot; "
                "lsblk -D shows DISC-GRAN > 0 once in effect"
            )

    class Arch:
        """mkinitcpio and the UKI cmdline: no packages."""


def with_discard(cmdline: str) -> str | None:
    """CMDLINE with discard in rd.luks.options for each rd.luks.name= uuid,
    added to its options or as a new option at the end; None when there is
    no rd.luks.name=."""
    uuids = re.findall(r"\brd\.luks\.name=([0-9a-fA-F-]+)=", cmdline)
    if not uuids:
        return None
    for uuid in uuids:
        options = re.search(rf"\brd\.luks\.options={uuid}:(\S*)", cmdline)
        if options is None:
            cmdline = f"{cmdline.rstrip()} rd.luks.options={uuid}:discard"
        elif "discard" not in options.group(1).split(","):
            cmdline = f"{cmdline[: options.end()]},discard{cmdline[options.end() :]}"
    return cmdline
