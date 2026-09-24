"""Arch Linux: pacman, set up before any install (its options, multilib,
makepkg's build flags, fresh mirrors)."""

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from dotfiles import engine
from dotfiles.engine import (
    as_root,
    changed,
    die,
    ensure_file,
    ensure_line,
    notice,
    output,
    retrying,
    run,
)
from dotfiles.platforms import transaction
from dotfiles.platforms.linux import Linux

# pacman's field names are translated; the parser reads the English ones.
C = {**os.environ, "LC_ALL": "C"}
PACMAN_CONF = "/etc/pacman.conf"
PARU = "https://aur.archlinux.org/paru.git"
STALE = "if downloads returned 404 the sync databases are stale: run {} -Syu and apply again"


class Arch(Linux):
    def __init__(self, cfg: dict):
        super().__init__(cfg)
        self._direct: dict[str, set[str]] = {}  # package -> Depends On, per apply

    def setup(self) -> None:
        features = self.cfg["features"]
        if features["pacman"]["enabled"]:
            self._pacman()
        if features["makepkg"]["enabled"]:
            self._makepkg()
        if features["reflector"]["enabled"]:
            self._reflector()

    def _pacman(self) -> None:
        pacman = self.cfg["features"]["pacman"]
        options = "/etc/pacman.conf.d/options.conf"
        ensure_file(
            options, f"ParallelDownloads = {pacman['parallel_downloads']}\n", owner="root:root"
        )
        # Options after the first repository section would be ignored.
        include = f"Include = {options}"
        ensure_line(PACMAN_CONF, f"^{re.escape(include)}$", include, before=r"^\[(?!options\])")
        conf = engine.path(PACMAN_CONF)
        lines = conf.read_text().splitlines() if conf.exists() else []  # a dry run on nothing
        if not pacman["multilib"] or "[multilib]" in lines:
            return  # a [multilib] enabled in pacman.conf itself is left alone
        multilib = "/etc/pacman.conf.d/multilib.conf"
        ensure_file(multilib, "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n", owner="root:root")
        include = f"Include = {multilib}"
        ensure_line(PACMAN_CONF, f"^{re.escape(include)}$", include)
        # Keyed on the database, not the line just added, so a sync the network
        # cut off is redone. -Syu, not -Sy: -Sy then -S is a partial upgrade.
        if not engine.path("/var/lib/pacman/sync/multilib.db").exists():
            transaction()
            for attempt in retrying():
                with attempt, as_root():
                    run("pacman", "-Syu", "--noconfirm")
            changed("multilib database synced (pacman -Syu)")

    def _makepkg(self) -> None:
        makepkg = self.cfg["features"]["makepkg"]
        lines = [f'MAKEFLAGS="-j{_jobs(makepkg["jobs"])}"']
        if makepkg["options"]:
            lines.append(f"OPTIONS+=({' '.join(makepkg['options'])})")
        git = self.cfg["git"]
        lines.append(f'PACKAGER="{git["name"]} <{git["email"]}>"')
        ensure_file("/etc/makepkg.conf.d/dotfiles.conf", "\n".join(lines) + "\n", owner="root:root")

    def _reflector(self) -> None:
        reflector = self.cfg["features"]["reflector"]
        edits = []
        if missing := self.missing(["reflector"]):
            changed(f"packages: {' '.join(missing)} (missing)")
            self.install(missing)
            edits.append(True)
        args = ["--save /etc/pacman.d/mirrorlist"]
        if reflector["country"]:
            args.append(f"--country {','.join(reflector['country'])}")
        for key in ("protocol", "latest", "sort", "age", "completion_percent", "download_timeout"):
            args.append(f"--{key.replace('_', '-')} {reflector[key]}")
        conf = "\n".join(args) + "\n"
        edits.append(ensure_file("/etc/xdg/reflector/reflector.conf", conf, owner="root:root"))
        timer = (
            f"[Timer]\nOnCalendar=\nOnCalendar={reflector['on_calendar']}\n"
            f"OnBootSec=\nOnBootSec={reflector['on_boot_sec']}\n"
        )
        override = "/etc/systemd/system/reflector.timer.d/override.conf"
        if ensure_file(override, timer, owner="root:root"):
            with as_root():
                run("systemctl", "daemon-reload")
            edits.append(True)
        edits.append(self.ensure_service("reflector.timer"))
        # Something changed: refresh now, before the install downloads,
        # rather than at the timer's next run.
        if any(edits):
            try:
                with as_root():
                    run("systemctl", "start", "reflector.service")
                changed("mirrorlist refreshed")
            except subprocess.CalledProcessError:
                notice(
                    "refreshing the mirrorlist failed (network?) — the old one stays, "
                    "reflector.timer tries again"
                )

    def missing(self, names: list[str]) -> list[str]:
        if not names:
            return []
        found = output("pacman", "-T", *names)  # prints exactly the ones not installed
        return list(names) if found is None else found.split()

    def install(self, names: list[str], replaces: list[str] = ()) -> None:
        for name in replaces:
            # -Qq also answers for a package that only provides NAME (rustup for rust).
            if output("pacman", "-Qq", name) == name:
                transaction()
                with as_root():
                    run("pacman", "-Rdd", "--noconfirm", name)
                changed(f"removed {name}, its replacement follows")
        known = _parse(output("pacman", "-Si", *names, env=C) or "") if names else {}
        repo = [n for n in names if n in known]
        aur = [n for n in names if n not in known]
        if repo:
            self._sync(repo)
        if not aur:
            return
        if not self.cfg["features"]["aur"]["enabled"]:
            die(f"not in the repositories: {' '.join(aur)} — enable features.aur to build them")
        self.ensure_paru()
        # paru runs as the user and calls sudo itself: the same one run() would.
        sudo = engine._sudo()
        flags = ["--sudo", sudo[0]] if sudo else []
        if sudo[1:]:
            flags += ["--sudoflags", " ".join(sudo[1:])]
        transaction()
        try:
            for attempt in retrying():
                with attempt:
                    run("paru", *flags, "-S", "--needed", "--noconfirm", *aur)
        except subprocess.CalledProcessError:
            die(f"paru -S failed; {STALE.format('paru')}")

    def ensure_paru(self) -> bool:
        """paru runs. A paru left behind by a libalpm bump does not, so the
        check is paru --version, not the package."""
        if (output("paru", "--version") or "").startswith("paru "):
            return False
        if engine.DRY_RUN:  # nothing cloned to read the dependencies from
            changed("paru built from the AUR")
            return True
        self._sync(self.missing(["base-devel", "git"]))
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "paru"
            for attempt in retrying():
                with attempt:
                    shutil.rmtree(src, ignore_errors=True)  # a clone cut off halfway
                    run("git", "clone", "--quiet", "--depth", "1", PARU, str(src))
            info = (src / ".SRCINFO").read_text()
            deps = re.findall(r"^\s*(?:make)?depends = (\S+)$", info, re.MULTILINE)
            self._sync(self.missing(sorted({re.split(r"[<>=]", d)[0] for d in deps})), "--asdeps")
            # cargo through rustup runs only with a default toolchain, and the
            # feature that sets one runs after the packages.
            if output("rustup", "default") == "":
                for attempt in retrying():
                    with attempt:
                        run("rustup", "default", "stable")
            # makepkg as the user (it refuses root), the install as root.
            run("makepkg", "--noconfirm", cwd=src)
            built = (output("makepkg", "--packagelist", cwd=src) or "").split()
            transaction()
            with as_root():
                run("pacman", "-U", "--noconfirm", *[f for f in built if Path(f).exists()])
        changed("paru built from the AUR")
        return True

    def _sync(self, names: list[str], *flags: str) -> None:
        """NAMES from the repositories, as root, retried; nothing when empty."""
        if not names:
            return
        transaction()
        try:
            for attempt in retrying():
                with attempt, as_root():
                    run("pacman", "-S", "--needed", "--noconfirm", *flags, *names)
        except subprocess.CalledProcessError:
            die(f"pacman -S failed; {STALE.format('pacman')}")

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


def _jobs(value: str) -> str:
    """ "NN%" of the cores, at least 1; anything else verbatim, for makepkg's
    shell to evaluate at every build ("$(nproc)")."""
    if value.endswith("%") and value[:-1].isdigit():
        return str(max(1, int(value[:-1]) * (os.cpu_count() or 1) // 100))
    return value
