"""fonts on Arch: packages, Nerd Fonts from their release, and fontconfig's preferences."""

import re
import shutil
from pathlib import Path
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.render import template
from dotfiles.retry import retrying

_NERD = ".local/share/fonts/nerd-fonts"
_CONF = "~/.config/fontconfig/conf.d/50-dotfiles.conf"
_STAMP = ".source"  # the URL a font's directory holds
_HINTING = ("none", "slight", "medium", "full")
_SUBPIXEL = ("rgb", "bgr", "vrgb", "vbgr", "none")
_FAMILY = (lambda v: re.fullmatch(r"[^<>&\n]+", v), "a font family, e.g. JetBrainsMono Nerd Font")


class Fonts(Feature):
    """The packages, each Nerd Font from its URL once, and our fontconfig file."""

    rules: ClassVar[dict[str, tuple]] = {
        "packages": (
            lambda v: all(re.fullmatch(r"[A-Za-z0-9@._+-]+", p) for p in v),
            "package names",
        ),
        "nerd_fonts": (
            lambda v: all(re.fullmatch(r"[A-Za-z0-9_-]+", f) for f in v),
            'names of the release\'s archives, e.g. "JetBrainsMono"',
        ),
        "nerd_version": (lambda v: re.fullmatch(r"[A-Za-z0-9._-]+", v), 'a tag, e.g. "v3.5.1"'),
        "nerd_url": (
            lambda v: (
                re.fullmatch(r"https://[^\s{}]*(\{(name|version)\}[^\s{}]*)*", v) and "{name}" in v
            ),
            "an https URL of a tar archive with {name}, and {version} if it has one",
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
        """Each Nerd Font not from its URL downloaded, fc-cache after; our fontconfig file."""
        system, home, settings = self.system, Path.home(), self.settings
        nerd = system.files.path(home / _NERD)
        urls = {
            n: settings["nerd_url"].format(name=n, version=settings["nerd_version"])
            for n in settings["nerd_fonts"]
        }
        fresh = [n for n, url in urls.items() if not _holds(nerd / n, url)]
        for name in fresh:
            self._download(name, urls[name], nerd / name)
        if fresh:  # the packages' fonts pacman's fontconfig hook caches itself
            system.shell.run("fc-cache", str(nerd))
        text = template(_CONF, fonts=self.settings)
        system.files.ensure(home / _CONF.removeprefix("~/"), text)

    def _download(self, name: str, url: str, dst: Path) -> None:
        """NAME's archive at URL unpacked into DST in place of what is there."""
        system = self.system
        if not system.shell.dry_run:
            archive = dst / ".download"
            for attempt in retrying(system.report):
                with attempt:
                    shutil.rmtree(dst, ignore_errors=True)  # another source, a half download
                    dst.mkdir(parents=True)
                    system.shell.run("curl", "-fsSL", "--output", str(archive), url)
            # No -J: tar finds the compression from the archive itself.
            system.shell.run("tar", "-xf", str(archive), "-C", str(dst))
            archive.unlink(missing_ok=True)
            (dst / _STAMP).write_text(f"{url}\n")
        system.report.changed(f"Nerd Font {name} from {url}")


def _holds(dst: Path, url: str) -> bool:
    """DST holds the font downloaded from URL."""
    stamp = dst / _STAMP
    return stamp.is_file() and stamp.read_text().strip() == url
