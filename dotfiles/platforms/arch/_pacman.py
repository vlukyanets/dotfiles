"""pacman: installs from the repositories, and the dependency graph."""

import os
import re
import subprocess
from collections.abc import Sequence

from dotfiles.engine import die
from dotfiles.platforms.arch._aur import Aur
from dotfiles.platforms.package_manager import PackageManager
from dotfiles.retry import retrying


def _c_env() -> dict[str, str]:
    """The environment as it is now, in the C locale: the parser reads English field names."""
    return {**os.environ, "LC_ALL": "C"}


class Pacman(PackageManager):
    """pacman: the repositories, one transaction per install, root through as_root."""

    def missing(self, names: list[str]) -> list[str]:
        """NAMES that are not installed (pacman -T). A check: no root, no change."""
        if not names:
            return []
        found = self.shell.output("pacman", "-T", *names)  # prints exactly the ones not installed
        return list(names) if found is None else found.split()

    def install(self, names: list[str], replaces: Sequence[str] = ()) -> list[str]:
        """REPLACES removed, then NAMES of the repositories installed in one transaction;
        the others, left for build(): the AUR.
        """
        self._remove(replaces)
        known = (
            self._parse(self.shell.output("pacman", "-Si", *names, env=_c_env()) or "")
            if names
            else {}
        )
        self.sync([n for n in names if n in known])
        return [n for n in names if n not in known]

    def build(self, names: list[str]) -> None:
        """NAMES built from the AUR as this user and installed as root, AUR dependencies first."""
        Aur(self).install(names)

    def upgrade(self) -> None:
        """pacman -Syu as root: the sync and the downloads retried, the install once.

        Never -Sy alone, which then -S is a partial upgrade.
        """
        for attempt in retrying(self.report):
            with attempt, self.shell.as_root():
                self.shell.run("pacman", "-Syuw", "--noconfirm")
        with self.shell.as_root():
            self.shell.run("pacman", "-Su", "--noconfirm")

    def direct(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its Depends On, from the sync databases, else the local one."""
        return self._field(names, "Depends On")

    def provides(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its Provides (sh for bash), from the sync databases, else the local one."""
        return self._field(names, "Provides")

    def _field(self, names: list[str], field: str) -> dict[str, set[str]]:
        """Each of NAMES -> the names in FIELD of pacman -Si, else -Qi; set() if unknown."""
        found: dict[str, set[str]] = {}
        for query in ("-Si", "-Qi"):
            rest = [n for n in names if n not in found]
            if rest:
                info = self.shell.output("pacman", query, *rest, env=_c_env()) or ""
                found.update(self._parse(info, field))
        return {n: found.get(n, set()) for n in names}

    def _remove(self, replaces: Sequence[str]) -> None:
        """Each of REPLACES installed under that very name removed, as root."""
        for name in replaces:
            # -Qq also answers for a package that only provides NAME (rustup for rust).
            if self.shell.output("pacman", "-Qq", name) == name:
                with self.shell.as_root():
                    self.shell.run("pacman", "-Rdd", "--noconfirm", name)
                self.report.changed(f"removed {name}, its replacement follows")

    def sync(self, names: list[str], *flags: str) -> None:
        """NAMES from the repositories with FLAGS, as root: downloaded with retries, installed once."""
        if not names:
            return
        try:
            for attempt in retrying(self.report):  # the network: a conflict fails the install
                with attempt, self.shell.as_root():
                    self.shell.run("pacman", "-Sw", "--needed", "--noconfirm", *names)
        except subprocess.CalledProcessError:
            die(
                "pacman -Sw failed; if downloads returned 404 the sync databases are stale:"
                " run pacman -Syu and apply again"
            )
        with self.shell.as_root():
            self.shell.run("pacman", "-S", "--needed", "--noconfirm", *flags, *names)

    @staticmethod
    def _parse(info: str, field: str = "Depends On") -> dict[str, set[str]]:
        """pacman -Si/-Qi output -> {Name: the names in FIELD, without versions}."""
        result = {}
        for record in info.split("\n\n"):
            fields = dict(re.findall(r"^(\S[^:\n]*?)\s*: (.*)$", record, re.MULTILINE))
            if "Name" in fields:
                deps = fields.get(field, "None").split()
                result[fields["Name"]] = {re.split(r"[<>=]", d)[0] for d in deps if d != "None"}
        return result
