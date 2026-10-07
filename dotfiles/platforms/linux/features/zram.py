"""zram on every Linux: compressed swap in RAM by zram-generator, and the vm sysctls that suit it."""

from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template

_CONF = "/etc/systemd/zram-generator.conf"
_UNIT = "systemd-zram-setup@zram0.service"  # the generator's, from the [zram0] of _CONF


class Zram(Feature):
    """zram0 as swap above the swap file; swappiness and watermarks only where set."""

    rules: ClassVar[dict[str, tuple]] = {
        # 0 up: the swap file has none, so the kernel's negative one, and zram fills first.
        "priority": (lambda v: 0 <= v <= 32767, "0 to 32767, above the swap file's"),
        "swappiness": (lambda v: 0 <= v <= 200, "0 to 200"),
        "watermark_scale_factor": (lambda v: 0 <= v <= 3000, "0 to 3000"),
    }

    def packages(self) -> list[str]:
        """The generator that makes zram0 from the config."""
        return ["zram-generator"]

    def apply(self) -> None:
        """The config, zram0 set up again when it changed; the unit on; the sysctls asked for."""
        system, zram = self.system, self.settings
        if system.files.ensure(_CONF, template(_CONF, zram=zram), owner="root:root"):
            with system.shell.as_root():
                system.shell.run("systemctl", "daemon-reload")
                system.shell.run("systemctl", "restart", _UNIT)
        system.ensure_service(_UNIT)
        if zram["swappiness"]:
            system.ensure_sysctl("vm.swappiness", zram["swappiness"])
            # One page per swap-in: read-ahead pays on a disk, not on RAM.
            system.ensure_sysctl("vm.page-cluster", 0)
        if zram["watermark_scale_factor"]:
            system.ensure_sysctl("vm.watermark_scale_factor", zram["watermark_scale_factor"])
