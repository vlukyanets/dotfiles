"""uv with one managed CPython, so `uv run` works offline after the apply."""

from dotfiles.engine import changed, network, output
from dotfiles.feature import Feature


class Uv(Feature):
    def apply(self, strategy):
        if output("uv", "python", "list", "--only-installed", "--managed-python"):
            return
        network("uv", "python", "install", failure="uv: installing CPython failed")
        changed("uv: default CPython installed")

    class Arch:
        def packages(self):
            return ["uv"]
