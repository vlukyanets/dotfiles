"""Finding classes in modules by name: this machine's platform, every platform.

A platform is a package, `platforms/<name>/`, holding its OperatingSystem
subclass (`ArchLinuxOs`, with the os-release `id` it runs on) and its
`features/`; `linux/` holds `LinuxOs`, the base the others fall back to.
"""

import importlib
import pkgutil
import platform
from inspect import isabstract

from dotfiles.engine import Machine
from dotfiles.errors import ConfigError
from dotfiles.platforms.operating_system import OperatingSystem


def _class_name(name: str) -> str:
    """The class a module NAME holds: packaging -> Packaging, nvidia_driver -> NvidiaDriver."""
    return name.title().replace("_", "")


def named(module, name: str, base: type, what: str) -> type:
    """The BASE class of MODULE named after NAME; WHAT names it in the error."""
    found = getattr(module, _class_name(name), None)
    if not (isinstance(found, type) and issubclass(found, base)):
        raise ConfigError(f"{module.__name__}: no {what} class {_class_name(name)}")
    return found


def detect(machine: Machine) -> OperatingSystem:
    """This machine's platform on MACHINE: the one whose id is os-release's ID, else ID_LIKE's."""
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    ids = [release.get("ID", ""), *release.get("ID_LIKE", "").split()]
    known = {cls.id: cls for cls in platforms()}
    for id in filter(None, ids):
        if id in known:
            return known[id](machine)
    raise ConfigError(f"no platform for {' or '.join(filter(None, ids)) or 'this system'}")


def _descendants(cls: type) -> list[type]:
    """Every subclass of CLS, at any depth."""
    return [c for sub in cls.__subclasses__() for c in (sub, *_descendants(sub))]


def platforms() -> list[type[OperatingSystem]]:
    """Every concrete platform under platforms/, by name: ArchLinuxOs; LinuxOs, a base, is none."""
    for info in pkgutil.iter_modules(importlib.import_module(__package__).__path__):
        if info.ispkg:
            importlib.import_module(f"{__package__}.{info.name}")
    found = {
        cls
        for cls in _descendants(OperatingSystem)
        if cls.__module__.startswith(f"{__package__}.") and not isabstract(cls)
    }
    return sorted(found, key=lambda cls: cls.__name__)


def every(machine: Machine) -> list[OperatingSystem]:
    """An instance of every concrete platform on MACHINE, for checks that cover them all."""
    return [cls(machine) for cls in platforms()]
