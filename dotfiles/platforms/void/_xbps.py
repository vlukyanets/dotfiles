"""xbps: installs from the repositories, and the dependency graph."""

import re
from collections.abc import Sequence

from dotfiles.platforms.package_manager import PackageManager
from dotfiles.retry import retrying


def _name(pattern: str) -> str:
    """The package of an xbps pattern or pkgver: glibc>=2.41_1, zsh-5.9.2_1 -> glibc, zsh."""
    name = re.split(r"[<>=]", pattern)[0]
    return re.sub(r"-[^-]+_\d+$", "", name) if name == pattern else name


class Xbps(PackageManager):
    """xbps: the repositories, synced before each install, one transaction per install."""

    def missing(self, names: list[str]) -> list[str]:
        """NAMES that are not installed (xbps-query -l). A check: no root, no change."""
        if not names:
            return []
        out = self.shell.output("xbps-query", "-l") or ""
        installed = {_name(line.split()[1]) for line in out.splitlines() if line.startswith("ii ")}
        return [n for n in names if n not in installed]

    def install(self, names: list[str], replaces: Sequence[str] = ()) -> list[str]:
        """The repositories synced, REPLACES removed, then NAMES of the repositories installed
        in one transaction; the others left, for build() to fail on.
        """
        # Here, not in setup(): an apply with nothing to install needs no root.
        for attempt in retrying(self.report):
            with attempt, self.shell.as_root():
                self.shell.run("xbps-install", "-S")
        for name in replaces:
            if not self.missing([name]):
                with self.shell.as_root():
                    self.shell.run("xbps-remove", "-y", name)
                self.report.changed(f"removed {name}, its replacement follows")
        known = [n for n in names if self.shell.output("xbps-query", "-R", "-p", "pkgver", n)]
        if known:
            for attempt in retrying(self.report):  # the network
                with attempt, self.shell.as_root():
                    self.shell.run("xbps-install", "-y", "-D", *known)
            with self.shell.as_root():
                self.shell.run("xbps-install", "-y", *known)
        return [n for n in names if n not in known]

    def upgrade(self) -> None:
        """xbps-install -Su as root: the sync and the downloads retried, the install once."""
        for attempt in retrying(self.report):
            with attempt, self.shell.as_root():
                self.shell.run("xbps-install", "-Syu", "-D")
        with self.shell.as_root():
            self.shell.run("xbps-install", "-yu")

    def direct(self, names: list[str]) -> dict[str, set[str]]:
        """Each of NAMES -> its run-time dependencies (xbps-query -R -x); set() if unknown."""
        return {
            n: {_name(d) for d in (self.shell.output("xbps-query", "-R", "-x", n) or "").split()}
            for n in names
        }
