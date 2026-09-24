"""systemd-oomd for a desktop: earlier pressure kills, for user sessions
only, and a swap kill as the last stop."""

from dotfiles.engine import as_root, ensure_file, run
from dotfiles.feature import Feature

ROOT = "root:root"


class Oomd(Feature):
    def apply(self, strategy):
        edits = [
            # 20 s of >60% pressure instead of the stock 30 s: on a laptop, the
            # difference between a stalled desktop and a killed tab.
            ensure_file(
                "/etc/systemd/oomd.conf.d/10-pressure.conf",
                "[OOM]\nDefaultMemoryPressureLimit=60%\nDefaultMemoryPressureDurationSec=20s\n",
                owner=ROOT,
            ),
            # The largest swap user dies once swap is 90% full, before the kernel's OOM killer.
            ensure_file(
                "/etc/systemd/system/-.slice.d/10-oomd.conf",
                "[Slice]\nManagedOOMSwap=kill\n",
                owner=ROOT,
            ),
            # Pressure kills user sessions only: a runaway browser or build, no service.
            ensure_file(
                "/etc/systemd/system/user@.service.d/10-oomd.conf",
                "[Service]\nManagedOOMMemoryPressure=kill\nManagedOOMMemoryPressureLimit=50%\n",
                owner=ROOT,
            ),
        ]
        if any(edits):
            with as_root():
                run("systemctl", "daemon-reload")
                # oomd.conf.d is read when oomd starts, not on daemon-reload.
                run("systemctl", "try-restart", "systemd-oomd.service")
        strategy.ensure_service("systemd-oomd.service")

    class Linux:
        """Part of systemd: no packages."""
