"""packaging on Arch: pacman and makepkg drop-ins in their .conf.d directories."""

import os
import re
from typing import ClassVar

from dotfiles.engine import die
from dotfiles.feature import Feature
from dotfiles.render import template

_PACMAN_CONF = "/etc/pacman.conf"
_PACMAN_OPTIONS_CONF = "/etc/pacman.conf.d/options.conf"
_PACMAN_MULTILIB_CONF = "/etc/pacman.conf.d/multilib.conf"
_MAKEPKG_DOTFILES_CONF = "/etc/makepkg.conf.d/dotfiles.conf"

# The options pacman.conf takes without a value.
_PACMAN_FLAGS = (
    "CheckSpace",
    "Color",
    "DisableDownloadTimeout",
    "DisableSandbox",
    "ILoveCandy",
    "NoProgressBar",
    "UseSyslog",
    "VerbosePkgLists",
)


class Packaging(Feature):
    """No packages, no requirements; the drop-ins and multilib."""

    rules: ClassVar[dict[str, tuple]] = {
        "pacman.parallel_downloads": (lambda v: v >= 0, "0 or more"),
        "pacman.flags": (
            lambda v: set(v) <= set(_PACMAN_FLAGS),
            f"names from {', '.join(_PACMAN_FLAGS)}",
        ),
        "makepkg.jobs": (
            lambda v: v >= 0 if type(v) is int else re.fullmatch(r"[1-9][0-9]*%", v),
            'a number of threads, or a percent of the cores like "50%"',
        ),
        "makepkg.packager": (
            lambda v: v == "" or re.fullmatch(r"[^<>]+ <[^<>]+>", v),
            '"Name <email>"',
        ),
    }
    either: ClassVar[dict[str, tuple[type, ...]]] = {"makepkg.jobs": (int, str)}

    def apply(self) -> None:
        """The drop-ins written and included; multilib on or off as set, synced when on."""
        pacman, makepkg = self.settings["pacman"], self.settings["makepkg"]
        files = self.system.files
        conf = files.path(_PACMAN_CONF)  # missing only in a dry run on an empty sysroot
        if pacman["multilib"] and conf.exists() and "[multilib]" in conf.read_text().splitlines():
            # A second [multilib] section makes pacman refuse to register the database.
            die(f"{_PACMAN_CONF} enables [multilib] itself: comment that section out")
        text = template(_PACMAN_OPTIONS_CONF, pacman=pacman)
        files.ensure(_PACMAN_OPTIONS_CONF, text, owner="root:root")
        # Options after the first repository section would be ignored.
        self._include(_PACMAN_OPTIONS_CONF, before=r"^\[(?!options\])")
        # Written either way, so turning multilib off takes the repository out again.
        text = template(_PACMAN_MULTILIB_CONF, multilib=pacman["multilib"])
        files.ensure(_PACMAN_MULTILIB_CONF, text, owner="root:root")
        self._include(_PACMAN_MULTILIB_CONF)
        if pacman["multilib"] and not files.path("/var/lib/pacman/sync/multilib.db").exists():
            self.system.manager.upgrade()  # -Syu, not -Sy: syncs the new repository
            self.system.report.changed("multilib database synced (pacman -Syu)")
        text = template(_MAKEPKG_DOTFILES_CONF, makepkg=makepkg, jobs=_jobs(makepkg["jobs"]))
        files.ensure(_MAKEPKG_DOTFILES_CONF, text, owner="root:root")

    def _include(self, dropin: str, before: str | None = None) -> None:
        """`Include = DROPIN` in pacman.conf, before the line matching BEFORE or at the end."""
        line = f"Include = {dropin}"
        self.system.files.line(_PACMAN_CONF, f"^{re.escape(line)}$", line, before=before)


def _jobs(value: int | str) -> int:
    """VALUE in threads: an integer as is, "NN%" that share of the CPUs, at least 1."""
    if isinstance(value, str):
        return max(1, int(value.removesuffix("%")) * (os.cpu_count() or 1) // 100)
    return value
