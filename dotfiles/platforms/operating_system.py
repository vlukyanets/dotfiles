"""The base of every platform: an operating system and its package manager."""

from abc import ABC, abstractmethod
from typing import ClassVar

from dotfiles.engine import Machine
from dotfiles.platforms.package_manager import PackageManager


class OperatingSystem(ABC):
    """An operating system: its package manager and the helpers every feature there can use."""

    id: ClassVar[str] = ""  # the os-release ID it runs on; a base has none

    @property
    @abstractmethod
    def manager_class(self) -> type[PackageManager]:
        """The package manager of this system; a concrete platform names it."""

    def __init__(self, machine: Machine):
        """The platform on MACHINE, and its package manager; features get their settings apart."""
        self.machine = machine
        self.shell, self.files, self.report = machine.shell, machine.files, machine.report
        self.manager = self.manager_class(machine)
