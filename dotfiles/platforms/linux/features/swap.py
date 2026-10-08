"""swap on every Linux: a swap file on its own btrfs subvolume, mounted and on by systemd units."""

import os
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
_SIZES = "KMGTPE"  # mkswapfile's suffixes, each 1024 times the one before


def _bytes(size: str) -> int:
    """SIZE as mkswapfile takes it, in bytes: "4g" -> 4294967296."""
    digits, unit = re.fullmatch(rf"(\d+)([{_SIZES}]?)", size, re.IGNORECASE).groups()
    return int(digits) * 1024 ** (_SIZES.index(unit.upper()) + 1 if unit else 0)


def _pages(n: int) -> int:
    """N bytes down to whole pages: a swap file uses no more, however it was made."""
    return n // os.sysconf("SC_PAGE_SIZE")


def _shown(n: int) -> str:
    """N bytes in the largest suffix that divides them: 2147483648 -> "2g"."""
    for power in range(len(_SIZES), 0, -1):
        if n % 1024**power == 0:
            return f"{n // 1024**power}{_SIZES[power - 1].lower()}"
    return str(n)


class Swap(Feature):
    """@swap mounted on /swap, the swap file in it of the size set and on; units, not fstab."""

    rules: ClassVar[dict[str, tuple]] = {
        "size": (lambda v: v == "" or re.fullmatch(r"\d+[KMGTPEkmgtpe]?", v), 'a size like "20g"'),
    }

    def packages(self) -> list[str]:
        """btrfs itself: subvolumes and mkswapfile."""
        return ["btrfs-progs"]

    def apply(self) -> None:
        """The subvolume, the units, the file of its size; checks first, so a wrong host changes nothing."""
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
        swapfile = files.path(_SWAPFILE)
        if not swapfile.exists():
            with shell.as_root():
                self._mkswapfile(size)
            system.report.changed(f"created {_SWAPFILE} ({size})")
        elif _pages(have := swapfile.stat().st_size) != _pages(_bytes(size)):
            self._recreate(size, have)
        system.ensure_service(_SWAP)
        fstab = files.path("/etc/fstab")
        if fstab.exists() and re.search(
            rf"^[^#]*\s{_MOUNTPOINT}(/swapfile)?\s", fstab.read_text(), re.MULTILINE
        ):
            system.report.notice(
                f"/etc/fstab still has a line for {_MOUNTPOINT} or {_SWAPFILE}:"
                " the systemd units own both now, remove it"
            )

    def _mkswapfile(self, size: str) -> None:
        """The swap file made, SIZE bytes, by btrfs: no holes, no copy-on-write."""
        self.system.shell.run(
            "btrfs", "filesystem", "mkswapfile", "--size", size, str(self.system.files.path(_SWAPFILE)),
            stdout=subprocess.DEVNULL,
        )  # fmt: skip

    def _recreate(self, size: str, have: int) -> None:
        """The swap file, HAVE bytes, made again with SIZE; left as it is while swapoff fails."""
        system = self.system
        shell = system.shell
        try:
            with shell.as_root():
                shell.run("systemctl", "stop", _SWAP)  # swapoff: its pages go back to RAM
        except subprocess.CalledProcessError:
            system.report.notice(
                f"{_SWAPFILE} is {_shown(have)}, not {size}: swapoff failed, its pages need"
                " free RAM; free some or reboot, the next apply recreates it"
            )
            return
        with shell.as_root():
            shell.run("rm", "-f", str(system.files.path(_SWAPFILE)))
            self._mkswapfile(size)
        system.report.changed(f"recreated {_SWAPFILE} ({_shown(have)} -> {size})")

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
