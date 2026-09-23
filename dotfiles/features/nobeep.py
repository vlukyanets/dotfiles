"""Silence the PC speaker."""

from dotfiles.engine import ensure_file, os_guard


def apply(cfg: dict) -> None:
    os_guard("arch")
    ensure_file("/etc/modprobe.d/nobeep.conf", "blacklist pcspkr\n", owner="root:root")
