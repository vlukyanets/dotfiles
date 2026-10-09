"""DKMS on Arch: dkms with the headers of every installed kernel, so it can build a module for each."""

from typing import ClassVar

from dotfiles.feature import Feature

_MODULES = "/usr/lib/modules"


class Dkms(Feature):
    """dkms and `<pkgbase>-headers` of each kernel under /usr/lib/modules."""

    # Its headers are there before the AUR builds a module (hardware.graphics requires it).
    before_packages: ClassVar[bool] = True

    def _kernels(self) -> list[str]:
        """The package of each installed kernel: the pkgbase file in its modules' directory."""
        found = self.system.files.path(_MODULES).glob("*/pkgbase")
        return sorted({name for path in found if (name := path.read_text().strip())})

    def packages(self) -> list[str]:
        """dkms and each kernel's headers. Read from the machine, not the host: its kernels are
        its own, and one installed later gets its headers on the next apply.
        """
        return ["dkms", *(f"{kernel}-headers" for kernel in self._kernels())]

    def apply(self) -> None:
        """Nothing to change: a notice when no kernel is found, since DKMS then builds nothing."""
        if not self._kernels():
            self.system.report.notice(f"no kernel in {_MODULES}: DKMS builds no module")
