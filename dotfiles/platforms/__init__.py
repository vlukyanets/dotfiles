"""Platforms: what differs between systems, each done with its own tools.

A platform module is named after an os-release ID (arch.py for ID=arch) and
defines one Platform subclass. Features never run a package manager or
systemctl themselves; they call the platform, through their strategy.
"""

import importlib
import importlib.util
import platform
from abc import ABC, abstractmethod
from contextlib import contextmanager
from contextvars import ContextVar

from dotfiles import engine
from dotfiles.config import ConfigError

PACKAGE = "dotfiles.platforms"
# Set inside `with watching(hook):`; run by transaction().
_hooks: ContextVar[tuple] = ContextVar("hooks", default=())


@contextmanager
def watching(hook):
    """HOOK() runs right before every package change inside the block, from
    any platform instance: the system or a feature's strategy."""
    token = _hooks.set((*_hooks.get(), hook))
    try:
        yield
    finally:
        _hooks.reset(token)


def transaction() -> None:
    """Packages are about to change: what watches runs first. A platform
    calls it before each command that installs, upgrades or removes a
    package; nothing on a dry run, which changes none."""
    if not engine.DRY_RUN:
        for hook in _hooks.get():
            hook()


class Platform(ABC):
    def __init__(self, cfg: dict):
        self.cfg = cfg  # the resolved config

    def setup(self) -> None:  # noqa: B027 — optional: most platforms need nothing
        """The package manager ready to install; once per apply."""

    def packages(self) -> list[str]:
        """A strategy's packages on this platform, in its own names."""
        return []

    def replaces(self) -> list[str]:
        """Installed packages a strategy's packages replace: removed just
        before those are installed, where they would conflict."""
        return []

    @abstractmethod
    def missing(self, names: list[str]) -> list[str]:
        """NAMES that are not installed. A check: no root, no change."""

    @abstractmethod
    def install(self, names: list[str], replaces: list[str] = ()) -> None:
        """NAMES installed, in one transaction, REPLACES removed first."""

    @abstractmethod
    def depends(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> every package it needs, transitively."""


def classes(module) -> list[type]:
    """The classes MODULE itself defines, in the order it defines them."""
    return [
        value
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__
    ]


def detect(cfg: dict, package: str = PACKAGE) -> Platform:
    """This machine's platform: the module named after os-release's ID, else
    after the first of ID_LIKE that has one."""
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
