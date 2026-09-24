"""libvirt and QEMU with virt-manager, the user in the libvirt group and
the default NAT network started and autostarting."""

import re
import subprocess

from dotfiles import engine
from dotfiles.engine import as_root, changed, notice, output, run
from dotfiles.feature import Feature

VIRSH = ("virsh", "-c", "qemu:///system")


class Libvirt(Feature):
    def apply(self, strategy):
        cpuinfo = engine.path("/proc/cpuinfo")
        text = cpuinfo.read_text() if cpuinfo.exists() else ""
        if not re.search(r"^flags\s*:.*\b(vmx|svm)\b", text, re.MULTILINE):
            notice(
                "libvirt: no vmx/svm CPU flag — hardware virtualisation is off in firmware, "
                "guests would run under slow TCG emulation"
            )
        strategy.ensure_service("libvirtd.service")
        strategy.ensure_service("virtlogd.socket")
        strategy.ensure_group_member("libvirt")
        info = self._network()
        if info is None:
            return
        with as_root():
            if not re.search(r"^Autostart:\s*yes", info, re.MULTILINE):
                run(*VIRSH, "net-autostart", "default", stdout=subprocess.DEVNULL)
                changed("libvirt default network autostart")
            if not re.search(r"^Active:\s*yes", info, re.MULTILINE):
                run(*VIRSH, "net-start", "default", stdout=subprocess.DEVNULL)
                changed("libvirt default network started")

    def _network(self) -> str | None:
        """virsh net-info of the default network; None when it is not defined.
        Readable as the user once the group membership is live, until then
        (this login) as root."""
        info = output(*VIRSH, "net-info", "default")
        if info or engine.DRY_RUN:
            return info or None
        try:
            with as_root():
                return run(*VIRSH, "net-info", "default", capture_output=True).stdout
        except subprocess.CalledProcessError:
            return None

    class Arch:
        def packages(self):
            return [
                "libvirt", "qemu-desktop", "pipewire-jack", "virt-manager", "dnsmasq",
                "edk2-ovmf", "swtpm",
            ]  # fmt: skip

        def replaces(self):
            return ["jack2"]  # qemu-desktop needs jack: pipewire-jack, which conflicts with it
