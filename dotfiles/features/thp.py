"""Transparent hugepages: the mode persisted through tmpfiles.d and set
live, plus an optional static reservation."""

from dotfiles import engine
from dotfiles.engine import as_root, changed, ensure_file, run
from dotfiles.feature import Feature

SYSFS = "/sys/kernel/mm/transparent_hugepage/enabled"
CONF = "/etc/tmpfiles.d/thp.conf"


class Thp(Feature):
    def apply(self, strategy):
        thp = self.cfg["features"]["thp"]
        ensure_file(CONF, f"w {SYSFS} - - - - {thp['mode']}\n", owner="root:root")
        live = engine.path(SYSFS)
        # The selected mode is the bracketed one: "always [madvise] never".
        if f"[{thp['mode']}]" not in (live.read_text() if live.exists() else ""):
            with as_root():
                run("systemd-tmpfiles", "--create", CONF)
            changed(f"transparent_hugepage = {thp['mode']}")
        if thp["reserve"] > 0:
            strategy.ensure_sysctl("vm.nr_hugepages", thp["reserve"])

    class Linux:
        """A kernel setting: no packages."""
