"""The AUR: packages built by makepkg as the user, then installed by pacman as root."""

import json
import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from dotfiles.engine import die
from dotfiles.retry import retrying

if TYPE_CHECKING:
    from dotfiles.platforms.arch._pacman import Pacman

_RPC = "https://aur.archlinux.org/rpc/v5/info"
_GIT = "https://aur.archlinux.org/{}.git"
# makepkg needs them for any build; installed explicitly, not as dependencies.
_TOOLS = ["base-devel", "git"]
# No -s: it would call sudo pacman itself; install() brought the dependencies.
# --force: a package of the same version, built against an older library, again;
# --cleanbuild and --clean: no build tree before or after, only the sources;
# --nocheck: no check(), so no checkdepends to install.
_MAKEPKG = ("makepkg", "--noconfirm", "--force", "--cleanbuild", "--clean", "--nocheck")


def _name(dep: str) -> str:
    """DEP without its version: `foo>=1.2` -> `foo`."""
    return re.split(r"[<>=]", dep)[0]


def _src(pkgbase: str) -> Path:
    """Where PKGBASE is built, kept between builds; not /tmp, whose tmpfs may be too small."""
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    return cache / "dotfiles" / "aur" / pkgbase


class Aur:
    """Builds as the user, installs as root; the repositories' side goes through PACMAN."""

    def __init__(self, pacman: "Pacman"):
        """Commands through PACMAN's shell; repository packages through PACMAN itself."""
        self.shell, self.report = pacman.shell, pacman.report
        self.pacman = pacman

    def install(self, names: list[str]) -> None:
        """NAMES built and installed, with the AUR packages they need first."""
        if os.geteuid() == 0:
            die("makepkg refuses root: run apply as a user, it asks sudo for the install")
        infos, order, repo = self._resolve(names)
        self.pacman.sync(self.pacman.missing(_TOOLS))
        self.pacman.sync(sorted(repo), "--asdeps")
        built: set[str] = set()
        for name in order:
            base = infos[name]["PackageBase"]
            if base in built:
                continue
            built.add(base)
            wanted = [n for n in order if infos[n]["PackageBase"] == base]
            self._install(self._build(base), wanted, explicit=set(names))
            self.report.changed(f"{' '.join(wanted)} built from the AUR")

    def _resolve(self, names: list[str]) -> tuple[dict[str, dict], list[str], set[str]]:
        """AUR info of NAMES and of the AUR packages they need; their build order, deps
        first; the repository packages they need that are missing.
        """
        infos: dict[str, dict] = {}
        needs: dict[str, list[str]] = {}  # AUR package -> the AUR packages it needs
        repo: set[str] = set()
        todo = list(names)
        while todo:
            infos.update(found := self._info(todo))
            todo = []
            for name, info in found.items():
                # No checkdepends: makepkg runs with --nocheck.
                deps = info.get("Depends", []) + info.get("MakeDepends", [])
                needs[name] = []
                for dep in self.pacman.missing(deps):  # pacman -T: versions and provides
                    if _name(dep) in infos or _name(dep) in todo:
                        needs[name].append(_name(dep))
                    elif self.shell.output("pacman", "-Sp", "--print-format", "%n", _name(dep)):
                        repo.add(_name(dep))  # a provider in the repositories, too
                    else:
                        needs[name].append(_name(dep))
                        todo.append(_name(dep))
        order: list[str] = []

        def visit(name: str, path: list[str]) -> None:
            """NAME after everything it needs."""
            if name in order:
                return
            if name in path:
                die(f"AUR packages need each other: {' → '.join([*path, name])}")
            for dep in needs[name]:
                visit(dep, [*path, name])
            order.append(name)

        for name in names:
            visit(name, [])
        return infos, order, repo

    def _info(self, names: list[str]) -> dict[str, dict]:
        """NAMES -> their AUR info; fails naming those the AUR does not have."""
        url = f"{_RPC}?{urlencode([('arg[]', n) for n in names])}"
        for attempt in retrying(self.report):
            with attempt:
                out = self.shell.run("curl", "-fsSL", url, capture_output=True).stdout
        found = {info["Name"]: info for info in json.loads(out)["results"]}
        if unknown := [n for n in names if n not in found]:
            die(f"not in the repositories nor the AUR: {' '.join(unknown)}")
        return found

    def _build(self, base: str) -> list[str]:
        """PKGBASE's AUR repo brought up to date and built by makepkg as this user; the files.

        Its directory stays between builds: git fetches only new commits, and
        makepkg keeps a source file that is already there and passes its checksum.
        """
        src, shell = _src(base), self.shell
        for attempt in retrying(self.report):
            with attempt:
                if (src / ".git").is_dir():
                    shell.run("git", "fetch", "--quiet", "--depth", "1", "origin", cwd=src)
                    shell.run("git", "reset", "--quiet", "--hard", "FETCH_HEAD", cwd=src)
                else:
                    shutil.rmtree(src, ignore_errors=True)  # a clone cut off halfway
                    shell.run(
                        "git", "clone", "--quiet", "--depth", "1", _GIT.format(base), str(src)
                    )
        # The packages of earlier builds; their source files stay.
        # ponytail: old sources pile up in each directory; prune by source= if it matters.
        for old in src.glob("*.pkg.tar*"):
            old.unlink()
        for attempt in retrying(self.report):  # its sources come from the network
            with attempt:
                shell.run(*_MAKEPKG, cwd=src)
        listed = (shell.output("makepkg", "--packagelist", cwd=src) or "").split()
        # It lists debug packages too, built only with makepkg's debug option.
        if not (built := [f for f in listed if Path(f).exists()]):
            die(f"makepkg built no package of {base} (it listed: {' '.join(listed) or 'nothing'})")
        return built

    def _install(self, files: list[str], wanted: list[str], explicit: set[str]) -> None:
        """The FILES of WANTED installed as root; those not in EXPLICIT as dependencies.

        No --needed: a package of the same version is installed again, the point of
        building one that stopped working.
        """
        by_name = {self.shell.output("pacman", "-Qqp", f): f for f in files}
        if missing := [n for n in wanted if n not in by_name]:
            die(f"makepkg built no {' '.join(missing)}")
        for asdeps in (False, True):
            chosen = [by_name[n] for n in wanted if (n not in explicit) == asdeps]
            if chosen:
                flags = ["--asdeps"] if asdeps else []
                with self.shell.as_root():
                    self.shell.run("pacman", "-U", "--noconfirm", *flags, *chosen)
