"""rustup on Arch: Linux's, in place of the rust package."""

from dotfiles.platforms.linux.features.development import rustup


class Rustup(rustup.Rustup):
    """Linux's rustup; pacman will not install it beside rust, which it conflicts with."""

    def replaces(self) -> list[str]:
        """rust."""
        return ["rust"]
