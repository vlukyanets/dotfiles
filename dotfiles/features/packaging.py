import os
import re

from dotfiles import engine
from dotfiles.engine import changed, die, ensure_file, ensure_line
from dotfiles.feature import Feature
from dotfiles.render import template

PACMAN_CONF = "/etc/pacman.conf"
OPTIONS = "/etc/pacman.conf.d/options.conf"
MULTILIB = "/etc/pacman.conf.d/multilib.conf"
MAKEPKG = "/etc/makepkg.conf.d/dotfiles.conf"


class Packaging(Feature):
    """pacman and makepkg settings, as drop-ins in their .conf.d directories."""

    class Arch:
        """Arch only; no packages, no requirements."""

    def apply(self, strategy) -> None:
        """The drop-ins written and included; multilib enabled and synced if set."""
        packaging = self.cfg["features"]["packaging"]
        pacman, makepkg = packaging["pacman"], packaging["makepkg"]
        conf = engine.path(PACMAN_CONF)
        lines = conf.read_text().splitlines() if conf.exists() else []  # a dry run on nothing
        if pacman["multilib"] and "[multilib]" in lines:
            # A second [multilib] section makes pacman refuse to register the database.
            die(f"{PACMAN_CONF} enables [multilib] itself: comment that section out")
        ensure_file(OPTIONS, template(OPTIONS, pacman=pacman), owner="root:root")
        # Options after the first repository section would be ignored.
        include(OPTIONS, before=r"^\[(?!options\])")
        if pacman["multilib"]:
            ensure_file(MULTILIB, template(MULTILIB), owner="root:root")
            include(MULTILIB)
            sync_multilib(strategy)
        text = template(MAKEPKG, makepkg=makepkg, jobs=jobs(makepkg["jobs"]))
        ensure_file(MAKEPKG, text, owner="root:root")


def include(dropin: str, before: str | None = None) -> None:
    """`Include = DROPIN` in pacman.conf, before the line matching BEFORE or at the end."""
    line = f"Include = {dropin}"
    ensure_line(PACMAN_CONF, f"^{re.escape(line)}$", line, before=before)


def sync_multilib(strategy) -> None:
    """A full upgrade while the multilib database is missing: it syncs the new repository."""
    if engine.path("/var/lib/pacman/sync/multilib.db").exists():
        return
    strategy.manager.upgrade()
    changed("multilib database synced (pacman -Syu)")


def jobs(value: int | str) -> int:
    """VALUE in threads: an integer as is, "NN%" that share of the CPUs, at least 1."""
    if isinstance(value, str):
        return max(1, int(value.removesuffix("%")) * (os.cpu_count() or 1) // 100)
    return value
