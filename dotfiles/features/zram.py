"""zram swap through zram-generator, with the vm sysctls that suit
compressed in-memory swap (no seek: swap eagerly, one page at a time)."""

from dotfiles.engine import as_root, ensure_file, run
from dotfiles.feature import Feature

UNIT = "systemd-zram-setup@zram0.service"


class Zram(Feature):
    def apply(self, strategy):
        zram = self.cfg["features"]["zram"]
        conf = (
            f"[zram0]\nzram-size = {zram['size']}\n"
            f"compression-algorithm = {zram['algorithm']}\nswap-priority = {zram['priority']}\n"
        )
        if ensure_file("/etc/systemd/zram-generator.conf", conf, owner="root:root"):
            with as_root():
                run("systemctl", "daemon-reload")
                run("systemctl", "restart", UNIT)
        strategy.ensure_service(UNIT)
        if zram["swappiness"] > 0:
            strategy.ensure_sysctl("vm.swappiness", zram["swappiness"])
            strategy.ensure_sysctl("vm.page-cluster", 0)
        if zram["watermark_scale_factor"] > 0:
            strategy.ensure_sysctl("vm.watermark_scale_factor", zram["watermark_scale_factor"])

    class Arch:
        def packages(self):
            return ["zram-generator"]
