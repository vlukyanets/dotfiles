"""rustup on Arch: cargo and rustc from rustup, with a stable default toolchain."""

from dotfiles.feature import Feature
from dotfiles.retry import retrying


class Rustup(Feature):
    """rustup in place of rust, and a default toolchain, without which cargo does not run."""

    def packages(self) -> list[str]:
        """rustup, which provides cargo and rustc."""
        return ["rustup"]

    def replaces(self) -> list[str]:
        """rust, which conflicts with rustup."""
        return ["rust"]

    def apply(self) -> None:
        """`rustup default stable` while rustup has no default toolchain."""
        if self.system.shell.output("rustup", "default"):
            return
        for attempt in retrying(self.system.report):
            with attempt:
                self.system.shell.run("rustup", "default", "stable")
        self.system.report.changed("rustup default stable")
