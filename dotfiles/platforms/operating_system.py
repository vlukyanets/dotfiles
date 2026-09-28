"""The base of every platform: an operating system and its package manager."""

from abc import ABC, abstractmethod

from dotfiles.platforms.package_manager import PackageManager


class Platform(ABC):
    """An operating system: its package manager and the helpers every feature there can use."""

    @property
    @abstractmethod
    def manager_class(self) -> type[PackageManager]:
        """The package manager of this system; a concrete platform names it."""

    def __init__(self, cfg: dict, manager: PackageManager | None = None):
        """The platform with the resolved CFG; MANAGER shared with the system, else a new one."""
        self.cfg = cfg  # the resolved config
        self.manager = manager or self.manager_class()
