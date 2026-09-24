"""Arch Linux: pacman. Its setup (pacman.conf, mirrors, the AUR) comes with
the packages module."""

import os
import re

from dotfiles.engine import as_root, output, retrying, run
from dotfiles.platforms.linux import Linux

# pacman's field names are translated; the parser reads the English ones.
C = {**os.environ, "LC_ALL": "C"}


class Arch(Linux):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._direct: dict[str, set[str]] = {}  # package -> Depends On, per apply

    def missing(self, names: list[str]) -> list[str]:
        if not names:
            return []
        found = output("pacman", "-T", *names)  # prints exactly the ones not installed
        return list(names) if found is None else found.split()

    def install(self, names: list[str]) -> None:
        for attempt in retrying():
            with attempt, as_root():
                run("pacman", "-S", "--needed", "--noconfirm", *names)

    def depends(self, names: list[str]) -> dict[str, set[str]]:
        todo = set(names)
        while todo := todo - self._direct.keys():
            self._direct.update(self._depends_on(sorted(todo)))
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

    def _depends_on(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its direct dependencies, from the sync database
        and, for what is not there (built locally, from the AUR), the local
        one. Version constraints are dropped; a name pacman knows nowhere
        needs nothing."""
        found: dict[str, set[str]] = {}
        for query in ("-Si", "-Qi"):
            rest = [n for n in names if n not in found]
            if rest:
                found.update(_parse(output("pacman", query, *rest, env=C) or ""))
        return {n: found.get(n, set()) for n in names}


def _parse(info: str) -> dict[str, set[str]]:
    """pacman -Si/-Qi output -> {Name: set of Depends On}."""
    result = {}
    for record in info.split("\n\n"):
        fields = dict(re.findall(r"^(\S[^:\n]*?)\s*: (.*)$", record, re.MULTILINE))
        if "Name" in fields:
            deps = fields.get("Depends On", "None").split()
            result[fields["Name"]] = {re.split(r"[<>=]", d)[0] for d in deps if d != "None"}
    return result
