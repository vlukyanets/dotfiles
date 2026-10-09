"""paru on Arch: the AUR helper, built from the AUR as the user and installed as root."""

from dotfiles.feature import Feature


class Paru(Feature):
    """paru built from the AUR while it does not run; cargo comes from rustup."""

    def requires(self) -> list[str]:
        """packaging: makepkg builds with its MAKEFLAGS and OPTIONS; rustup: cargo."""
        return ["packaging", "development.rustup"]

    def apply(self) -> None:
        """paru built and installed unless it runs."""
        # --version, not the package: a paru left behind by a libalpm bump does not run,
        # so it is not in packages(), which would see it installed.
        if (self.system.shell.output("paru", "--version") or "").startswith("paru "):
            return
        if self.system.shell.dry_run:  # nothing to resolve the AUR from without fetching
            self.system.report.changed("paru built from the AUR")
            return
        self.system.manager.build(["paru"])
