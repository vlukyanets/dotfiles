"""rustup with a stable default toolchain, so cargo works right after the
first apply."""

import subprocess

from dotfiles.engine import changed, network, output, run
from dotfiles.feature import Feature


class Rustup(Feature):
    def apply(self, strategy):
        if output("rustup", "default") == "":  # rustup runs, but without a default
            network("rustup", "default", "stable", failure="installing the stable toolchain failed")
            changed("rustup default stable")
        rustc = output("rustup", "run", "stable", "rustc", "-V") or ""
        cargo = output("rustup", "run", "stable", "cargo", "-V") or ""
        if not (rustc.startswith("rustc ") and cargo.startswith("cargo ")):
            try:
                run("rustup", "toolchain", "uninstall", "stable", stderr=subprocess.DEVNULL)
            except subprocess.CalledProcessError:
                pass  # half there or not there at all: the install below settles it
            network(
                "rustup", "toolchain", "install", "stable", failure="reinstalling stable failed"
            )
            changed("reinstalled the stable toolchain (rustc or cargo did not run)")

    class Arch:
        def packages(self):
            return ["rustup"]

        def replaces(self):
            return ["rust"]  # conflicts with rustup, which provides it
