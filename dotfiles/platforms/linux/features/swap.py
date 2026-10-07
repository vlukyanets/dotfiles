"""swap on every Linux: a swap file on its own btrfs subvolume, mounted and on by systemd units."""

import re
import subprocess
import tempfile
from typing import ClassVar

from dotfiles.engine import die
from dotfiles.feature import Feature
from dotfiles.render import template

# Its own subvolume: a swap file in a snapshotted one blocks its snapshots.
_SUBVOLUME = "@swap"
_MOUNTPOINT = "/swap"
_SWAPFILE = f"{_MOUNTPOINT}/swapfile"
# systemd's names for those paths: a unit is named after what it mounts or swaps on.
_MOUNT = "swap.mount"
_SWAP = "swap-swapfile.swap"
_UNITS = "/etc/systemd/system"


class Swap(Feature):
    """@swap mounted on /swap, the swap file in it created once and on; units, not fstab."""

    rules: ClassVar[dict[str, tuple]] = {
        "size": (lambda v: v == "" or re.fullmatch(r"\d+[KMGTPEkmgtpe]?", v), 'a size like "20g"'),
    }

    def packages(self) -> list[str]:
        """btrfs itself: subvolumes and mkswapfile."""
        return ["btrfs-progs"]

    def apply(self) -> None:
        """The subvolume, the units, the file, each once; checks first, so a wrong host changes nothing."""
        system = self.system
        files, shell = system.files, system.shell
        size = self.settings["size"]
        if not size:
            die('features.swap.size is empty: set it for this host, e.g. "20g"')
        fstype = shell.output("findmnt", "-no", "FSTYPE", "/")
        if fstype != "btrfs":
            die(f"/ is {fstype or 'unknown'}: the swap file lives on a btrfs subvolume")
        # Listing subvolumes needs root: looked at only while @swap is not mounted.
        if shell.output("systemctl", "is-active", _MOUNT) != "active":
            self._subvolume()
        names = {"subvolume": _SUBVOLUME, "mountpoint": _MOUNTPOINT, "swapfile": _SWAPFILE}
        names["uuid"] = shell.output("findmnt", "-no", "UUID", "/")
        # A list, not any(generator): both units are written, not just up to the first change.
        units = [
            files.ensure(
                f"{_UNITS}/{unit}", template(f"{_UNITS}/{unit}", **names), owner="root:root"
            )
            for unit in (_MOUNT, _SWAP)
        ]
        mountpoint = files.path(_MOUNTPOINT)
        with shell.as_root():
            if any(units):
                shell.run("systemctl", "daemon-reload")
            if not mountpoint.is_dir():
                shell.run("mkdir", "-p", str(mountpoint))
        system.ensure_service(_MOUNT)
        if not files.path(_SWAPFILE).exists():
            with shell.as_root():
                shell.run(
                    "btrfs", "filesystem", "mkswapfile", "--size", size, str(files.path(_SWAPFILE)),
                    stdout=subprocess.DEVNULL,
                )  # fmt: skip
            system.report.changed(f"created {_SWAPFILE} ({size})")
        system.ensure_service(_SWAP)
        fstab = files.path("/etc/fstab")
        if fstab.exists() and re.search(
            rf"^[^#]*\s{_MOUNTPOINT}(/swapfile)?\s", fstab.read_text(), re.MULTILINE
        ):
            system.report.notice(
                f"/etc/fstab still has a line for {_MOUNTPOINT} or {_SWAPFILE}:"
                " the systemd units own both now, remove it"
            )

    def _subvolume(self) -> None:
        """@swap at the top of the root filesystem, unless it is there."""
        system = self.system
        shell = system.shell
        if shell.dry_run:
            system.report.changed(
                f"subvolume {_SUBVOLUME}, unless it is there (listing needs root)"
            )
            return
        with shell.as_root():
            found = shell.run("btrfs", "subvolume", "list", "/", capture_output=True).stdout
        if re.search(rf" path {_SUBVOLUME}$", found, re.MULTILINE):
            return
        # findmnt prints the mounted subvolume after the device: /dev/vda2[/@].
        device = re.sub(r"\[.*\]$", "", shell.output("findmnt", "-no", "SOURCE", "/") or "")
        with tempfile.TemporaryDirectory() as top, shell.as_root():
            shell.run("mount", "-o", "subvolid=5", device, top)
            try:
                shell.run(
                    "btrfs", "subvolume", "create", f"{top}/{_SUBVOLUME}", stdout=subprocess.DEVNULL
                )
            finally:
                shell.run("umount", top)
        system.report.changed(f"created subvolume {_SUBVOLUME}")
