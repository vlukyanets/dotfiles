import subprocess

from dotfiles import engine
from dotfiles.engine import as_root, changed, defer, retrying, run
from dotfiles.feature import Feature


class Pkgfile(Feature):
    def apply(self, strategy):
        strategy.ensure_service("pkgfile-update.timer")
        # The timer only refreshes a database that exists: seed it once.
        cache = engine.path("/var/cache/pkgfile")
        if cache.is_dir() and any(cache.iterdir()):
            return
        try:
            for attempt in retrying():
                with attempt, as_root():
                    run("pkgfile", "-u")
        except subprocess.CalledProcessError:
            defer("downloading the pkgfile database failed")
        changed("pkgfile database created")

    class Arch:
        def packages(self):
            return ["pkgfile"]
