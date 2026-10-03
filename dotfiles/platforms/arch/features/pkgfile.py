"""pkgfile on Arch: which package has a file, from a database pkgfile-update.timer keeps fresh."""

import subprocess

from dotfiles.feature import Feature

_CACHE = "/var/cache/pkgfile"


class Pkgfile(Feature):
    """pkgfile installed, its timer on, and its database downloaded while there is none."""

    def packages(self) -> list[str]:
        """pkgfile itself."""
        return ["pkgfile"]

    def apply(self) -> None:
        """The timer on; `pkgfile --update` at once while the cache holds no database."""
        system = self.system
        system.ensure_service("pkgfile-update.timer")
        cache = system.files.path(_CACHE)
        if cache.is_dir() and any(cache.glob("*.files")):
            return
        # Now, not at the timer's next run: until then pkgfile finds nothing.
        try:
            with system.shell.as_root():
                system.shell.run("pkgfile", "--update")
        except subprocess.CalledProcessError:
            system.report.notice(
                "downloading pkgfile's database failed (network?): pkgfile-update.timer tries again"
            )
            return
        system.report.changed("pkgfile's database downloaded")
