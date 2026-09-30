"""The base class of every feature, and where a platform's features are found."""

import importlib
import pkgutil
from typing import ClassVar

from dotfiles.config import Checks
from dotfiles.platforms import discovery
from dotfiles.platforms.operating_system import OperatingSystem


class Feature:
    """A feature on one platform: its settings, what it declares there, what it does.

    Each platform has its own, in `<platform>/features/<name>.py`; a platform
    without one runs its base's (LinuxOs's). Each default is nothing.
    """

    # What the schema's types cannot say, under features.<name>: key -> (test, what it must be).
    rules: ClassVar[dict[str, tuple]] = {}
    # Keys that take either of several types; the default's type is the first.
    either: ClassVar[dict[str, tuple[type, ...]]] = {}

    def __init__(self, settings: dict, system: OperatingSystem):
        """The feature with SETTINGS, its features.<name> of the resolved config, on SYSTEM."""
        self.settings = settings
        self.system = system

    def packages(self) -> list[str]:
        """The packages it installs on this platform, in its own names."""
        return []

    def replaces(self) -> list[str]:
        """Installed packages its packages() replace, removed just before the install."""
        return []

    def requires(self) -> list[str]:
        """Features it needs: enabled, or check fails; they run first."""
        return []

    def apply(self) -> None:
        """What this feature does, once its packages are installed."""


def _package(package: str) -> dict[str, type[Feature]]:
    """Every feature class of PACKAGE by its module's name: packaging -> Packaging."""
    try:
        found = importlib.import_module(package)
    except ModuleNotFoundError as e:  # a platform without features of its own
        if e.name is None or not (package == e.name or package.startswith(e.name + ".")):
            raise
        return {}
    return {
        info.name: discovery.named(
            importlib.import_module(f"{package}.{info.name}"), info.name, Feature, "feature"
        )
        for info in sorted(pkgutil.iter_modules(found.__path__))
        if not info.name.startswith("_")  # a module its features share
    }


def classes(platform: type[OperatingSystem]) -> dict[str, type[Feature]]:
    """PLATFORM's features by name: its own, else the nearest base's (ArchLinuxOs, then LinuxOs)."""
    found: dict[str, type[Feature]] = {}
    for base in reversed(platform.__mro__):
        # arch/_os.py holds ArchLinuxOs: arch/features/ holds its features.
        package = importlib.import_module(base.__module__).__package__
        if issubclass(base, OperatingSystem) and package:
            found |= _package(f"{package}.features")
    return found


def every() -> list[tuple[str, type[Feature]]]:
    """(name, class) of every feature of every platform, for the config's checks."""
    return [
        (name, cls) for platform in discovery.platforms() for name, cls in classes(platform).items()
    ]


def checks() -> Checks:
    """The rules and either of every feature, under features.<name>: what config checks."""
    rules, either = {}, {}
    for name, cls in every():  # every platform's: the schema is theirs together
        rules |= {f"features.{name}.{key}": rule for key, rule in cls.rules.items()}
        either |= {f"features.{name}.{key}": types for key, types in cls.either.items()}
    return Checks(rules, either)
