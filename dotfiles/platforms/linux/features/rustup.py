"""rustup on every Linux: cargo and rustc from rustup, with the host's toolchain as the default."""

import re
from typing import ClassVar

from dotfiles.feature import Feature
from dotfiles.retry import retrying


class Rustup(Feature):
    """rustup in place of rust, and TOOLCHAIN the default, without which cargo does not run."""

    rules: ClassVar[dict[str, tuple]] = {
        "toolchain": (
            lambda v: re.fullmatch(r"[A-Za-z0-9._-]+", v),
            'a toolchain name: "stable", "nightly", "1.85.0", "nightly-2026-09-01"',
        ),
    }

    def packages(self) -> list[str]:
        """rustup, which provides cargo and rustc."""
        return ["rustup"]

    def executable(self) -> str:
        """The rustup to run: the package's, on the PATH."""
        return "rustup"

    def apply(self) -> None:
        """`rustup default TOOLCHAIN`, which installs it too, unless it is the default already."""
        shell, rustup = self.system.shell, self.executable()
        toolchain = self.settings["toolchain"]
        current = (shell.output(rustup, "default") or "").partition(" ")[0]
        # rustup names it with the host: stable-x86_64-unknown-linux-gnu.
        show = shell.output(rustup, "show") or ""
        host = re.search(r"^Default host: (\S+)$", show, re.MULTILINE)
        if current in (toolchain, f"{toolchain}-{host[1] if host else ''}"):
            return
        for attempt in retrying(self.system.report):  # a toolchain not installed is downloaded
            with attempt:
                shell.run(rustup, "default", toolchain)
        self.system.report.changed(f"rustup default {toolchain} (was {current or 'none'})")
