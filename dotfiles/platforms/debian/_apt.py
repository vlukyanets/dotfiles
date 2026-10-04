"""apt: installs from the repositories, and the dependency graph."""

import os
import re
from collections.abc import Sequence

from dotfiles.platforms.package_manager import PackageManager
from dotfiles.retry import retrying

# Root's environment for apt-get: no debconf questions, and sudo keeps nothing of ours.
_ENV = {"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "DEBIAN_FRONTEND": "noninteractive"}
_APT = ("apt-get", "-q", "-y")


def _c_env() -> dict[str, str]:
    """The environment as it is now, in the C locale: the parser reads English field names."""
    return {**os.environ, "LC_ALL": "C"}


class Apt(PackageManager):
    """apt: the repositories, synced before each install, one transaction per install."""

    def missing(self, names: list[str]) -> list[str]:
        """NAMES dpkg does not have installed. A check: no root, no change."""
        if not names:
            return []
        out = self.shell.output("dpkg-query", "-W", "-f=${Package} ${db:Status-Status}\n", *names)
        installed = {
            line.split()[0] for line in (out or "").splitlines() if line.endswith(" installed")
        }
        return [n for n in names if n not in installed]

    def install(self, names: list[str], replaces: Sequence[str] = ()) -> list[str]:
        """The package lists updated, REPLACES removed, then NAMES of the repositories installed
        in one transaction; the others left, for build() to fail on: Debian has no AUR.
        """
        self._update()  # here, not in setup(): an apply with nothing to install needs no root
        self._remove(replaces)
        known = {n for n in names if self._candidate(n)}
        ours = [n for n in names if n in known]
        if ours:
            for attempt in retrying(self.report):  # the network
                with attempt, self.shell.as_root():
                    self.shell.run(*_APT, "install", "--download-only", *ours, env=_ENV)
            with self.shell.as_root():
                self.shell.run(*_APT, "install", *ours, env=_ENV)
        return [n for n in names if n not in known]

    def upgrade(self) -> None:
        """apt-get update, then full-upgrade as root: the downloads retried, the install once."""
        self._update()
        for attempt in retrying(self.report):
            with attempt, self.shell.as_root():
                self.shell.run(*_APT, "full-upgrade", "--download-only", env=_ENV)
        with self.shell.as_root():
            self.shell.run(*_APT, "full-upgrade", env=_ENV)

    def direct(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its Depends and Pre-Depends, every alternative of them; set() if
        unknown.
        """
        out = self.shell.output("apt-cache", "depends", "-i", *names, env=_c_env()) or ""
        found: dict[str, set[str]] = {}
        current = None
        for line in out.splitlines():
            if not line.startswith(" "):
                current = found.setdefault(line, set())
            elif current is not None and (
                m := re.match(r"\s*\|?(?:Pre)?Depends: <?([^\s>]+)", line)
            ):
                current.add(m[1])
        return {n: found.get(n, set()) for n in names}

    def _candidate(self, name: str) -> bool:
        """Whether the repositories have NAME to install."""
        out = self.shell.output("apt-cache", "policy", name, env=_c_env()) or ""
        return bool(re.search(r"^  Candidate: (?!\(none\))", out, re.MULTILINE))

    def _update(self) -> None:
        """apt-get update as root, retried."""
        for attempt in retrying(self.report):
            with attempt, self.shell.as_root():
                self.shell.run(*_APT, "update", env=_ENV)

    def _remove(self, replaces: Sequence[str]) -> None:
        """Each of REPLACES that is installed removed, as root."""
        for name in replaces:
            if not self.missing([name]):
                with self.shell.as_root():
                    self.shell.run(*_APT, "remove", name, env=_ENV)
                self.report.changed(f"removed {name}, its replacement follows")
