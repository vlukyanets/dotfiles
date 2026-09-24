"""The NVIDIA driver for the GPU's generation and the running kernel's
flavour, plus nvtop. The GPU is read from sysfs and hwdata's pci.ids, so
the driver is known before any package is installed."""

import os
import re

from dotfiles import engine
from dotfiles.engine import notice
from dotfiles.feature import Feature

# Generation -> driver package and its 32-bit libraries, after nvidia-utils'
# support matrix; every branch but the current one comes from the AUR.
DRIVERS = [
    (r"RTX [2-9]\d{3}|GTX 16\d{2}|MX[3-9]\d{2}", "nvidia-dkms", "lib32-nvidia-utils"),
    (
        r"GTX 10\d{2}|GTX 9\d{2}|MX[12]\d{2}|\d{3}MX",
        "nvidia-580xx-dkms",
        "lib32-nvidia-580xx-utils",
    ),
    (r"GTX [67]\d{2}", "nvidia-470xx-dkms", "lib32-nvidia-470xx-utils"),
    (r"GTX [45]\d{2}", "nvidia-390xx-dkms", "lib32-nvidia-390xx-utils"),
    (r"GeForce [89]\d{2}|GeForce [123]\d{2}", "nvidia-340xx-dkms", None),
]
UNKNOWN = ("nvidia-dkms", "lib32-nvidia-utils")


class Nvidia(Feature):
    def apply(self, strategy):
        name = gpu()
        if name is None:
            return
        _, lib32, known = driver(name)
        if not known:
            notice(f"nvidia: unrecognised GPU generation ({name}), installed {UNKNOWN[0]}")
        if lib32 and not strategy.multilib():
            notice(
                f"nvidia: no {lib32} — features.pacman.multilib is off, so 32-bit apps get "
                "no GPU acceleration"
            )
        if not engine.path("/sys/module/nvidia").exists():
            notice("the NVIDIA driver is not loaded — reboot for it to take effect")

    class Arch:
        def packages(self):
            name = gpu()
            if name is None:
                return []
            package, lib32, _ = driver(name)
            extra = [lib32] if lib32 and self.multilib() else []
            return [package, headers(), *extra, "nvtop"]


def gpu() -> str | None:
    """The first NVIDIA display controller's name from pci.ids, "" when its
    id is not there; None without one."""
    for device in sorted(engine.path("/sys/bus/pci/devices").glob("*")):
        vendor, kind, id = ((device / f).read_text().strip() for f in ("vendor", "class", "device"))
        if vendor == "0x10de" and kind.startswith("0x03"):
            return _name("10de", id.removeprefix("0x"))
    return None


def _name(vendor: str, device: str) -> str:
    ids = engine.path("/usr/share/hwdata/pci.ids")
    text = ids.read_text(errors="replace") if ids.exists() else ""
    # A vendor line, then its devices, each indented by one tab.
    block = re.search(rf"^{vendor} .*\n((?:\t.*\n|#.*\n)*)", text, re.MULTILINE)
    found = re.search(rf"^\t{device}  (.*)$", block.group(1) if block else "", re.MULTILINE)
    return found.group(1) if found else ""


def driver(name: str) -> tuple[str, str | None, bool]:
    """GPU NAME -> (driver package, its 32-bit package, whether the
    generation was recognised)."""
    for pattern, package, lib32 in DRIVERS:
        if re.search(pattern, name, re.IGNORECASE):
            return package, lib32, True
    return *UNKNOWN, False


def headers() -> str:
    """DKMS builds against the running kernel's headers, not just linux's."""
    release = os.uname().release
    for flavour in ("zen", "lts", "hardened"):
        if f"-{flavour}" in release:
            return f"linux-{flavour}-headers"
    return "linux-headers"
