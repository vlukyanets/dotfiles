"""A swap file on its own btrfs subvolume (a swap file on / blocks
snapshots of /), mounted and activated by systemd units, not fstab."""

import re
import subprocess
import tempfile

from dotfiles import engine
from dotfiles.engine import as_root, changed, die, ensure_file, notice, output, run
from dotfiles.feature import Feature
from dotfiles.features.snapper import swap_files_on_root

SUBVOLUME = "@swap"
MOUNTPOINT = "/swap"
SWAPFILE = f"{MOUNTPOINT}/swapfile"
MOUNT = """[Unit]
Description=btrfs {subvolume} subvolume for the swap file

[Mount]
What=UUID={uuid}
Where={mountpoint}
Type=btrfs
Options=noatime,subvol=/{subvolume}

[Install]
WantedBy=local-fs.target
"""
SWAP = """[Unit]
Description=swap file on {subvolume}

[Swap]
What={swapfile}

[Install]
WantedBy=swap.target
"""


class Swap(Feature):
    def apply(self, strategy):
        size = self.cfg["features"]["swap"]["size"]
        if not size:
            die('features.swap.size is empty for this host — set it, e.g. "20g"')
        fstype = output("findmnt", "-no", "FSTYPE", "/")
        if fstype != "btrfs":
            die(f"/ is {fstype or 'unknown'}; swap files here live on btrfs subvolumes")
        # Listing subvolumes needs root: only look while the mount is not up,
        # the one case in which root is needed anyway.
        if output("systemctl", "is-active", "swap.mount") != "active":
            self._subvolume()

        uuid = output("findmnt", "-no", "UUID", "/")
        names = {"subvolume": SUBVOLUME, "mountpoint": MOUNTPOINT, "swapfile": SWAPFILE}
        units = [
            ensure_file(
                "/etc/systemd/system/swap.mount",
                MOUNT.format(uuid=uuid, **names),
                owner="root:root",
            ),
            ensure_file(
                "/etc/systemd/system/swap-swapfile.swap", SWAP.format(**names), owner="root:root"
            ),
        ]
        with as_root():
            if any(units):
                run("systemctl", "daemon-reload")
            if not engine.path(MOUNTPOINT).is_dir():
                run("mkdir", "-p", MOUNTPOINT)
        strategy.ensure_service("swap.mount")
        if not engine.path(SWAPFILE).exists():
            with as_root():
                run("btrfs", "filesystem", "mkswapfile", "--size", size, SWAPFILE,
                    stdout=subprocess.DEVNULL)  # fmt: skip
            changed(f"created {SWAPFILE} ({size})")
        strategy.ensure_service("swap-swapfile.swap")

        fstab = engine.path("/etc/fstab")
        entry = rf"^[^#]*\s{MOUNTPOINT}(/swapfile)?\s"
        if fstab.exists() and re.search(entry, fstab.read_text(), re.MULTILINE):
            notice(
                f"/etc/fstab still has a line for {MOUNTPOINT} or {SWAPFILE} — the systemd "
                "units own both now, remove it"
            )
        for other in swap_files_on_root():
            if other != SWAPFILE:
                notice(
                    f"active swap file {other} sits on the root subvolume — snapper fails with "
                    "'Text file busy' until it is moved or removed"
                )

    def _subvolume(self) -> None:
        """SUBVOLUME at the top of the root filesystem."""
        if engine.DRY_RUN:
            changed(f"subvolume {SUBVOLUME}, unless it exists (listing it needs root)")
            return
        with as_root():
            found = run("btrfs", "subvolume", "list", "/", capture_output=True)
        if re.search(rf" path {SUBVOLUME}$", found.stdout, re.MULTILINE):
            return
        device = re.sub(r"\[.*\]$", "", output("findmnt", "-no", "SOURCE", "/") or "")
        with tempfile.TemporaryDirectory() as top, as_root():
            run("mount", "-o", "subvolid=5", device, top)
            try:
                run("btrfs", "subvolume", "create", f"{top}/{SUBVOLUME}", stdout=subprocess.DEVNULL)
            finally:
                run("umount", top)
        changed(f"created subvolume {SUBVOLUME}")

    class Arch:
        def packages(self):
            return ["btrfs-progs"]
