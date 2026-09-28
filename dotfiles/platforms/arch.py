"""Arch Linux: packages through pacman, from the repositories."""

import os
import re
import subprocess

from dotfiles.engine import as_root, changed, die, output, retrying, run
from dotfiles.platforms.linux import Linux
from dotfiles.platforms.package_manager import PackageManager

# pacman's field names are translated; the parser reads the English ones.
C = {**os.environ, "LC_ALL": "C"}
STALE = "if downloads returned 404 the sync databases are stale: run {} -Syu and apply again"


class Pacman(PackageManager):
    """pacman: the repositories, one transaction per install, root through as_root."""

    def missing(self, names: list[str]) -> list[str]:
        """NAMES that are not installed (pacman -T). A check: no root, no change."""
        if not names:
            return []
        found = output("pacman", "-T", *names)  # prints exactly the ones not installed
        return list(names) if found is None else found.split()

    def install(self, names: list[str], replaces: list[str] = ()) -> None:
        """REPLACES removed, then NAMES installed in one transaction; fails first on unknown names."""
        self._remove(replaces)
        known = self.parse(output("pacman", "-Si", *names, env=C) or "") if names else {}
        if unknown := [n for n in names if n not in known]:
            die(f"not in the repositories: {' '.join(unknown)}")
        self._sync(names)

    def upgrade(self) -> None:
        """pacman -Syu, as root, retried: never -Sy alone, which then -S is a partial upgrade."""
        for attempt in retrying():
            with attempt, as_root():
                run("pacman", "-Syu", "--noconfirm")

    def direct(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its Depends On, from the sync databases, else the local one."""
        found: dict[str, set[str]] = {}
        for query in ("-Si", "-Qi"):
            rest = [n for n in names if n not in found]
            if rest:
                found.update(self.parse(output("pacman", query, *rest, env=C) or ""))
        return {n: found.get(n, set()) for n in names}

    def _remove(self, replaces: list[str]) -> None:
        """Each of REPLACES installed under that very name removed, as root."""
        for name in replaces:
            # -Qq also answers for a package that only provides NAME (rustup for rust).
            if output("pacman", "-Qq", name) == name:
                with as_root():
                    run("pacman", "-Rdd", "--noconfirm", name)
                changed(f"removed {name}, its replacement follows")

    def _sync(self, names: list[str]) -> None:
        """NAMES from the repositories, as root, retried; nothing when empty."""
        if not names:
            return
        try:
            for attempt in retrying():
                with attempt, as_root():
                    run("pacman", "-S", "--needed", "--noconfirm", *names)
        except subprocess.CalledProcessError:
            die(f"pacman -S failed; {STALE.format('pacman')}")

    @staticmethod
    def parse(info: str) -> dict[str, set[str]]:
        """pacman -Si/-Qi output -> {Name: set of Depends On}."""
        result = {}
        for record in info.split("\n\n"):
            fields = dict(re.findall(r"^(\S[^:\n]*?)\s*: (.*)$", record, re.MULTILINE))
            if "Name" in fields:
                deps = fields.get("Depends On", "None").split()
                result[fields["Name"]] = {re.split(r"[<>=]", d)[0] for d in deps if d != "None"}
        return result


class Arch(Linux):
    """Arch Linux: packages through pacman, from the repositories."""

    manager_class = Pacman
