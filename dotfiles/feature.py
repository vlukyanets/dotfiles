"""The base class of every feature, and where a platform's features are found."""

import importlib
import pkgutil
from typing import ClassVar, NamedTuple

from dotfiles.config import Checks
from dotfiles.errors import ConfigError
from dotfiles.platforms import discovery
from dotfiles.platforms.operating_system import OperatingSystem


class Setting(NamedTuple):
    """A setting another feature owns that a feature requires: KEY, under features., OP VALUE.

    For now VALUE is true or false and OP only "equal"; a key no file sets equals neither.
    """

    key: str
    value: bool
    op: str = "equal"


class Feature:
    """A feature on one platform: its settings, what it declares there, what it does.

    Each platform has its own, in `<platform>/features/<name>.py`; a platform
    without one runs its base's (LinuxOs's). Each default is nothing.
    """

    # What the schema's types cannot say, under features.<name>: key -> (test, what it must be).
    rules: ClassVar[dict[str, tuple]] = {}
    # Keys and their types where no default says it: several types, the
    # default's first, or none in the schema, so absent unless a file sets it.
    types: ClassVar[dict[str, tuple[type, ...]]] = {}
    # Runs before the package install, to make packages installable (a repository): its
    # apply() cannot need its own packages, and it requires only features that set it too.
    before_packages: ClassVar[bool] = False

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

    def requires(self) -> list[str | Setting]:
        """Features it needs, or settings of theirs: met, or check fails; they run first."""
        return []

    def apply(self) -> None:
        """What this feature does, once its packages are installed."""


def table(features: dict, name: str) -> dict | None:
    """The table of feature NAME, dotted, in FEATURES (the config's `features`); None if absent."""
    found = features
    for part in name.split("."):
        found = found.get(part) if isinstance(found, dict) else None
    return found if isinstance(found, dict) else None


def _package(package: str, prefix: str = "") -> dict[str, type[Feature]]:
    """Every feature class of PACKAGE and its groups by its dotted path: system.zram -> Zram."""
    try:
        found = importlib.import_module(package)
    except ModuleNotFoundError as e:  # a platform without features of its own
        if e.name is None or not (package == e.name or package.startswith(e.name + ".")):
            raise
        return {}
    classes: dict[str, type[Feature]] = {}
    for info in sorted(pkgutil.iter_modules(found.__path__)):
        if info.name.startswith("_"):  # a module or group its features share
            continue
        if info.ispkg:  # a group
            classes |= _package(f"{package}.{info.name}", f"{prefix}{info.name}.")
        else:
            module = importlib.import_module(f"{package}.{info.name}")
            classes[prefix + info.name] = discovery.named(module, info.name, Feature, "feature")
    return classes


def _where(cls: type) -> str:
    """CLS's module as a path from platforms/: arch/features/development/rustup.py."""
    return cls.__module__.removeprefix(f"{discovery.__package__}.").replace(".", "/") + ".py"


def classes(platform: type[OperatingSystem]) -> dict[str, type[Feature]]:
    """PLATFORM's features by name: its own, else the nearest base's (ArchLinuxOs, then LinuxOs).

    An own module of a name the base has too holds a subclass of the base's class.
    """
    found: dict[str, type[Feature]] = {}
    for base in reversed(platform.__mro__):
        # arch/_os.py holds ArchLinuxOs: arch/features/ holds its features.
        package = importlib.import_module(base.__module__).__package__
        if issubclass(base, OperatingSystem) and package:
            own = _package(f"{package}.features")
            for name, cls in own.items():
                if name in found and not issubclass(cls, found[name]):
                    platform_name = _where(found[name]).split("/")[0]
                    raise ConfigError(
                        f"{_where(cls)}: {cls.__name__} must subclass"
                        f" {platform_name}'s {found[name].__name__}"
                    )
            found |= own
    return found


def every() -> list[tuple[str, type[Feature]]]:
    """(name, class) of every feature of every platform, for the config's checks."""
    return [
        (name, cls) for platform in discovery.platforms() for name, cls in classes(platform).items()
    ]


def checks() -> Checks:
    """The rules and types of every feature, under features.<name>: what config checks."""
    rules, types = {}, {}
    for name, cls in every():  # every platform's: the schema is theirs together
        rules |= {f"features.{name}.{key}": rule for key, rule in cls.rules.items()}
        types |= {f"features.{name}.{key}": kinds for key, kinds in cls.types.items()}
    return Checks(rules, types)
