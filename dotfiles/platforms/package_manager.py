"""The base of every package manager: what it must answer, and the dependency graph."""

from abc import ABC, abstractmethod
from collections.abc import Sequence

from dotfiles.engine import Machine, die


class PackageManager(ABC):
    """How a system checks, installs and relates its packages; one per apply."""

    def __init__(self, machine: Machine):
        """Commands on MACHINE; an empty cache of each package's dependencies."""
        self.shell, self.report = machine.shell, machine.report
        self._direct: dict[str, set[str]] = {}  # package -> its direct dependencies

    def setup(self) -> None:  # noqa: B027 — optional: most managers need nothing
        """The package manager ready to install; once per apply."""

    @abstractmethod
    def missing(self, names: list[str]) -> list[str]:
        """NAMES that are not installed. A check: no root, no change."""

    @abstractmethod
    def install(self, names: list[str], replaces: Sequence[str] = ()) -> list[str]:
        """NAMES installed, in one transaction, REPLACES removed first; those it has not
        in its repositories, left for build().
        """

    def build(self, names: list[str]) -> None:
        """NAMES, which install() left, built and installed; none can be by default."""
        die(f"not in the repositories: {' '.join(names)}")

    @abstractmethod
    def upgrade(self) -> None:
        """Every installed package brought up to date, the databases synced first."""

    @abstractmethod
    def direct(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> the packages it depends on directly; set() if unknown."""

    def provides(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> the other names it can be depended on by; none by default."""
        return {name: set() for name in names}

    def depends(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> every package it needs, transitively; cached for the apply."""
        todo = set(names)
        while todo := todo - self._direct.keys():
            self._direct.update(self.direct(sorted(todo)))
            todo = set().union(*(self._direct[n] for n in todo))
        result = {}
        for name in names:
            seen: set[str] = set()
            stack = list(self._direct[name])
            while stack:
                dep = stack.pop()
                if dep not in seen:
                    seen.add(dep)
                    stack.extend(self._direct.get(dep, ()))
            result[name] = seen
        return result
