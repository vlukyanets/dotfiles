from dotfiles.feature import Feature


class Aur(Feature):
    """A paru that runs, whether or not a feature needs an AUR package; the
    platform builds it (install does too, when one does)."""

    def apply(self, strategy):
        strategy.ensure_paru()

    class Arch:
        """paru comes from the AUR, so it is no package here."""
