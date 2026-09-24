"""fnm with the current LTS node as the default and pnpm on it."""

from dotfiles.engine import changed, network, output, run
from dotfiles.feature import Feature

LTS = ("fnm", "exec", "--using=lts-latest", "--")


class Fnm(Feature):
    def apply(self, strategy):
        lts = [line for line in (output("fnm", "ls") or "").splitlines() if "lts-latest" in line]
        if not lts:
            network("fnm", "install", "--lts", failure="fnm: installing the LTS node failed")
            changed("fnm: LTS node installed")
        if not any("default" in line for line in lts):
            run("fnm", "default", "lts-latest")
            changed("fnm: default = lts-latest")
        if "pnpm@" not in (output(*LTS, "npm", "ls", "-g", "pnpm") or ""):
            network(*LTS, "npm", "install", "-g", "pnpm", failure="installing pnpm failed")
            changed("pnpm installed")

    class Arch:
        def packages(self):
            return ["fnm"]
