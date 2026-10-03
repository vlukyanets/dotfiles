"""fonts on Arch: packages, Nerd Fonts from their release, and fontconfig's preferences."""

import re
import shutil
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template
from dotfiles.retry import retrying

_RELEASE = "https://github.com/ryanoasis/nerd-fonts/releases/download"
_NERD = ".local/share/fonts/nerd-fonts"
_CONF = "~/.config/fontconfig/conf.d/50-dotfiles.conf"
_STAMP = ".version"  # the release a font's directory holds
_HINTING = ("none", "slight", "medium", "full")
_SUBPIXEL = ("rgb", "bgr", "vrgb", "vbgr", "none")
_FAMILY = (lambda v: re.fullmatch(r"[^<>&\n]+", v), "a font family, e.g. JetBrainsMono Nerd Font")


class Fonts(Feature):
    """The packages, each Nerd Font of the release once, and our fontconfig file."""

    rules: ClassVar[dict[str, tuple]] = {
        "packages": (
            lambda v: all(re.fullmatch(r"[A-Za-z0-9@._+-]+", p) for p in v),
            "package names",
        ),
        "nerd_fonts": (
            lambda v: all(re.fullmatch(r"[A-Za-z0-9_-]+", f) for f in v),
            'names of the release\'s archives, e.g. "JetBrainsMono"',
        ),
        "nerd_version": (
            lambda v: re.fullmatch(r"v\d+\.\d+\.\d+", v),
            'a release tag, e.g. "v3.5.1"',
        ),
        "default.monospace": _FAMILY,
        "default.sans_serif": _FAMILY,
        "default.serif": _FAMILY,
        "default.emoji": _FAMILY,
        "render.hinting": (lambda v: v in _HINTING, f"one of {', '.join(_HINTING)}"),
        "render.subpixel": (lambda v: v in _SUBPIXEL, f"one of {', '.join(_SUBPIXEL)}"),
    }
    # No defaults: what is not set stays fontconfig's own.
    types: ClassVar[dict[str, tuple[type, ...]]] = {
        "default.monospace": (str,),
        "default.sans_serif": (str,),
        "default.serif": (str,),
        "default.emoji": (str,),
        "render.antialias": (bool,),
        "render.hinting": (str,),
        "render.subpixel": (str,),
    }

    def packages(self) -> list[str]:
        """fontconfig for fc-cache, the packages, and curl for the Nerd Fonts."""
        curl = ["curl"] if self.settings["nerd_fonts"] else []
        return ["fontconfig", *self.settings["packages"], *curl]

    def apply(self) -> None:
        """Each Nerd Font not of the release downloaded, fc-cache after; our fontconfig file."""
        system, home = self.system, Path.home()
        version = self.settings["nerd_version"]
        nerd = system.files.path(home / _NERD)
        fresh = [n for n in self.settings["nerd_fonts"] if not _holds(nerd / n, version)]
        for name in fresh:
            self._download(name, version, nerd / name)
        if fresh:  # the packages' fonts pacman's fontconfig hook caches itself
            system.shell.run("fc-cache", str(nerd))
        text = template(_CONF, fonts=self.settings)
        system.files.ensure(home / _CONF.removeprefix("~/"), text)

    def _download(self, name: str, version: str, dst: Path) -> None:
        """NAME's archive of VERSION unpacked into DST in place of what is there."""
        system = self.system
        if not system.shell.dry_run:
            archive = dst / f"{name}.tar.xz"
            for attempt in retrying(system.report):
                with attempt:
                    shutil.rmtree(dst, ignore_errors=True)  # an older release, a half download
                    dst.mkdir(parents=True)
                    url = f"{_RELEASE}/{version}/{name}.tar.xz"
                    system.shell.run("curl", "-fsSL", "--output", str(archive), url)
            system.shell.run("tar", "-xJf", str(archive), "-C", str(dst))
            archive.unlink(missing_ok=True)
            (dst / _STAMP).write_text(f"{version}\n")
        system.report.changed(f"Nerd Font {name} {version} into {dst}")


def _holds(dst: Path, version: str) -> bool:
    """DST holds a Nerd Font of VERSION."""
    stamp = dst / _STAMP
    return stamp.is_file() and stamp.read_text().strip() == version
