"""paru on Arch: the AUR helper, built from the AUR as the user and installed as root."""

import os
import shutil
import tempfile
from pathlib import Path

from dotfiles.engine import die
from dotfiles.feature import Feature
from dotfiles.retry import retrying

_PARU = "https://aur.archlinux.org/paru.git"


class Paru(Feature):
    """base-devel and git for the build, cargo from rustup; paru built while it does not run."""

    def packages(self) -> list[str]:
        """What makepkg and paru's PKGBUILD need, but cargo."""
        return ["base-devel", "git"]

    def requires(self) -> list[str]:
        """packaging: makepkg builds with its MAKEFLAGS and OPTIONS; rustup: cargo."""
        return ["packaging", "rustup"]

    def apply(self) -> None:
        """paru built and installed unless it runs."""
        # --version, not the package: a paru left behind by a libalpm bump does not run.
        if (self.system.shell.output("paru", "--version") or "").startswith("paru "):
            return
        if self.system.shell.dry_run:  # nothing cloned to build from
            self.system.report.changed("paru built and installed")
            return
        if os.geteuid() == 0:
            die("makepkg refuses root: run apply as a user, it asks sudo for the install")
        # Not /tmp: a tmpfs there may be too small for cargo's build.
        cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "dotfiles"
        cache.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as tmp:
            built = self._build(Path(tmp) / "paru")
            self._install(built)
        self.system.report.changed("paru built and installed")

    def _build(self, src: Path) -> list[str]:
        """paru cloned into SRC and built by makepkg as this user; the package files."""
        shell = self.system.shell
        for attempt in retrying(self.system.report):
            with attempt:
                shutil.rmtree(src, ignore_errors=True)  # a clone cut off halfway
                shell.run("git", "clone", "--quiet", "--depth", "1", _PARU, str(src))
        # No -s: it would call sudo pacman itself; packages() installed the dependencies.
        for attempt in retrying(self.system.report):  # its sources come from the network
            with attempt:
                shell.run("makepkg", "--noconfirm", "--cleanbuild", cwd=src)
        listed = (shell.output("makepkg", "--packagelist", cwd=src) or "").split()
        # It names paru-debug too, which is built only with makepkg's debug option.
        if not (built := [f for f in listed if Path(f).exists()]):
            die(f"makepkg built no package (it listed: {' '.join(listed) or 'nothing'})")
        return built

    def _install(self, built: list[str]) -> None:
        """The package files BUILT installed by pacman as root."""
        with self.system.shell.as_root():
            self.system.shell.run("pacman", "-U", "--needed", "--noconfirm", *built)
