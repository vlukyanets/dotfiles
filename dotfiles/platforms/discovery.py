"""Finding classes in modules: this machine's platform, every platform."""

import importlib
import importlib.util
import pkgutil
import platform
from inspect import isabstract

from dotfiles.config import ConfigError
from dotfiles.platforms.operating_system import Platform

PACKAGE = "dotfiles.platforms"


def classes(module) -> list[type]:
    """The classes MODULE itself defines, in the order it defines them."""
    return [
        value
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
    ]


def detect(cfg: dict, package: str = PACKAGE) -> Platform:
    """This machine's platform, from os-release ID then ID_LIKE."""
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    ids = [release.get("ID", ""), *release.get("ID_LIKE", "").split()]
    for id in filter(None, ids):
        name = f"{package}.{id.replace('-', '_')}"
        if importlib.util.find_spec(name) is None:
            continue
        module = importlib.import_module(name)
        found = [c for c in classes(module) if issubclass(c, Platform)]
        if len(found) != 1:
            raise ConfigError(f"{name}: defines {len(found)} platforms, not one")
        return found[0](cfg)
    raise ConfigError(f"no platform for {' or '.join(filter(None, ids)) or 'this system'}")


def every(cfg: dict, package: str = PACKAGE) -> list[Platform]:
    """An instance of every concrete platform, for checks that cover them all."""
    found = []
    for info in sorted(pkgutil.iter_modules(importlib.import_module(package).__path__)):
        module = importlib.import_module(f"{package}.{info.name}")
        found += [c(cfg) for c in classes(module) if issubclass(c, Platform) and not isabstract(c)]
    return found
