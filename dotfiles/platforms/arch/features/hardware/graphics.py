"""The GPUs' drivers on Arch: Mesa's Vulkan per GPU, NVIDIA's through DKMS on its branch."""

from typing import ClassVar

from dotfiles.feature import Feature, Setting

# Per GPU: its packages, and of those the ones with a lib32- pair for 32-bit programs.
_GPUS = {
    "amd": (["mesa", "vulkan-radeon"], ["mesa", "vulkan-radeon"]),
    "intel": (["mesa", "vulkan-intel", "intel-media-driver"], ["mesa", "vulkan-intel"]),
    "nouveau": (["mesa", "vulkan-nouveau"], ["mesa", "vulkan-nouveau"]),
}
_LEGACY = ("580xx", "470xx", "390xx")  # the AUR's: Maxwell to Volta, Kepler, Fermi


def _nvidia(driver: str) -> tuple[list[str], list[str]]:
    """NVIDIA's packages on branch DRIVER, and the ones with a lib32- pair."""
    # nvidia-open-dkms is today's nvidia-dkms, which it provides: that name is no package.
    dkms, utils = (
        ("nvidia-open-dkms", "nvidia-utils")
        if driver == "current"
        else (f"nvidia-{driver}-dkms", f"nvidia-{driver}-utils")
    )
    # VA-API through NVDEC needs the 470 series or newer.
    libva = [] if driver == "390xx" else ["libva-nvidia-driver"]
    return [dkms, utils, *libva], [utils]


def _branch(driver: str) -> list[str]:
    """Every package of branch DRIVER, its lib32- ones and current's prebuilt modules too."""
    own, lib32 = _nvidia(driver)
    extra = ["nvidia-open", "nvidia-open-lts"] if driver == "current" else []
    return [*own, *(f"lib32-{p}" for p in lib32), *extra]


class Graphics(Feature):
    """The drivers of `gpus`, their 32-bit ones with `lib32`, NVIDIA's on `nvidia.driver`."""

    # Before the other packages: steam's vulkan-driver is then this, not --noconfirm's first.
    before_packages: ClassVar[bool] = True

    rules: ClassVar[dict[str, tuple]] = {
        "gpus": (
            lambda v: (
                set(v) <= {*_GPUS, "nvidia"}
                and len(set(v)) == len(v)
                and not {"nvidia", "nouveau"} <= set(v)
            ),
            "amd, intel, nvidia or nouveau, each once, not nvidia with nouveau (one card)",
        ),
        "nvidia.driver": (
            lambda v: v in ("current", *_LEGACY),
            "current, 580xx, 470xx or 390xx",
        ),
    }

    def _driver(self) -> str | None:
        """NVIDIA's branch while nvidia is among gpus, else None."""
        return self.settings["nvidia"]["driver"] if "nvidia" in self.settings["gpus"] else None

    def packages(self) -> list[str]:
        """Each GPU's packages, with their lib32- pairs when lib32 is on."""
        found: set[str] = set()
        for gpu in self.settings["gpus"]:
            own, lib32 = _nvidia(self._driver()) if gpu == "nvidia" else _GPUS[gpu]
            found.update(own)
            if self.settings["lib32"]:
                found.update(f"lib32-{p}" for p in lib32)
        return sorted(found)

    def replaces(self) -> list[str]:
        """The other NVIDIA branches' packages, so the chosen one installs without a conflict."""
        driver = self._driver()
        if driver is None:
            return []
        others = [b for b in ("current", *_LEGACY) if b != driver]
        return sorted({p for b in others for p in _branch(b)} - set(_branch(driver)))

    def requires(self) -> list[str | Setting]:
        """dkms for NVIDIA's module; multilib for the lib32- packages."""
        return [
            *(["system.dkms"] if self._driver() else []),
            *([Setting("packaging.pacman.multilib", True)] if self.settings["lib32"] else []),
        ]
