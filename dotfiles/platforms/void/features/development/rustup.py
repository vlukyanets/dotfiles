"""rustup on Void: the package has only rustup-init, which puts rustup in ~/.cargo/bin."""

import os
from pathlib import Path

from dotfiles.platforms.linux.features.development import rustup
from dotfiles.retry import retrying


class Rustup(rustup.Rustup):
    """Linux's rustup, once rustup-init has installed it for the user."""

    def executable(self) -> str:
        """~/.cargo/bin/rustup: not on this process's PATH until the next login."""
        return str(Path.home() / ".cargo" / "bin" / "rustup")

    def apply(self) -> None:
        """rustup-init with the toolchain unless rustup is there, then Linux's check."""
        system = self.system
        if not os.access(system.files.path(self.executable()), os.X_OK):
            toolchain = self.settings["toolchain"]
            # It adds ~/.cargo/bin to the PATH in ~/.profile and the shells' rc files.
            for attempt in retrying(system.report):
                with attempt:
                    system.shell.run("rustup-init", "-y", "--default-toolchain", toolchain)
            system.report.changed(f"rustup installed by rustup-init, default {toolchain}")
            if system.shell.dry_run:
                return  # nothing to ask rustup yet
        super().apply()
