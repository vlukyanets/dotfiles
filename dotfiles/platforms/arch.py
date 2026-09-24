"""Arch Linux: pacman, set up before any install (its options, multilib,
makepkg's build flags, fresh mirrors)."""

import os
import re

from dotfiles import engine
from dotfiles.engine import as_root, changed, ensure_file, ensure_line, output, retrying, run
from dotfiles.platforms.linux import Linux

# pacman's field names are translated; the parser reads the English ones.
C = {**os.environ, "LC_ALL": "C"}
PACMAN_CONF = "/etc/pacman.conf"


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

    def _pacman(self) -> None:
        pacman = self.cfg["features"]["pacman"]
        options = "/etc/pacman.conf.d/options.conf"
        ensure_file(
            options, f"ParallelDownloads = {pacman['parallel_downloads']}\n", owner="root:root"
        )
        # Options after the first repository section would be ignored.
        include = f"Include = {options}"
        ensure_line(PACMAN_CONF, f"^{re.escape(include)}$", include, before=r"^\[(?!options\])")
        conf = engine._path(PACMAN_CONF)
        lines = conf.read_text().splitlines() if conf.exists() else []  # a dry run on nothing
        if not pacman["multilib"] or "[multilib]" in lines:
            return  # a [multilib] enabled in pacman.conf itself is left alone
        multilib = "/etc/pacman.conf.d/multilib.conf"
        ensure_file(multilib, "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n", owner="root:root")
        include = f"Include = {multilib}"
        ensure_line(PACMAN_CONF, f"^{re.escape(include)}$", include)
        # Keyed on the database, not the line just added, so a sync the network
        # cut off is redone. -Syu, not -Sy: -Sy then -S is a partial upgrade.
        if not engine._path("/var/lib/pacman/sync/multilib.db").exists():
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


def _jobs(value: str) -> str:
    """ "NN%" of the cores, at least 1; anything else verbatim, for makepkg's
    shell to evaluate at every build ("$(nproc)")."""
    if value.endswith("%") and value[:-1].isdigit():
        return str(max(1, int(value[:-1]) * (os.cpu_count() or 1) // 100))
    return value
