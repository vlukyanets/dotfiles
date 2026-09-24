from dotfiles import engine
from dotfiles.engine import as_root, changed, network
from dotfiles.feature import Feature


class Pkgfile(Feature):
    def apply(self, strategy):
        strategy.ensure_service("pkgfile-update.timer")
        # The timer only refreshes a database that exists: seed it once.
        cache = engine.path("/var/cache/pkgfile")
        if cache.is_dir() and any(cache.iterdir()):
            return
        with as_root():
            network("pkgfile", "-u", failure="downloading the pkgfile database failed")
        changed("pkgfile database created")

    class Arch:
        def packages(self):
            return ["pkgfile"]
