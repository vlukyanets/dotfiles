"""snapper for /, snap-pac for pacman run by hand, and one snapshot pair
around an apply, taken only when it changes packages."""

import json
import os
import pwd
import re
import subprocess
from contextlib import contextmanager

from dotfiles import engine, platforms
from dotfiles.engine import as_root, changed, die, ensure_file, notice, output, run
from dotfiles.feature import Feature

SNAPPER = ("snapper", "-c", "root")
# Every snapshot of an apply: counted by the number cleanup, described.
NUMBERED = ("-c", "number", "-d", "dotfiles apply")
PACMAN_LOG = "/var/log/pacman.log"


class Snapper(Feature):
    def apply(self, strategy):
        snapper = self.cfg["features"]["snapper"]
        fstype = output("findmnt", "-no", "FSTYPE", "/")
        if fstype != "btrfs":
            die(f"/ is {fstype or 'unknown'}, snapper needs a btrfs root")
        for swapfile in swap_files_on_root():
            # btrfs refuses to snapshot it, and snap-pac only says "Creating snapshot failed".
            notice(
                f"active swap file {swapfile} sits on the root subvolume — every snapshot of / "
                "fails until it moves to its own subvolume (features.swap)"
            )
        if not engine.path("/etc/snapper/configs/root").exists():
            self._create_config()
        self._settings(
            {
                "TIMELINE_CREATE": "yes" if snapper["timeline"] else "no",
                "NUMBER_LIMIT": str(snapper["number_limit"]),
                "NUMBER_LIMIT_IMPORTANT": str(snapper["number_limit_important"]),
                # The user takes the apply's snapshots through snapperd, without
                # root; SYNC_ACL makes /.snapshots readable for the same user.
                "ALLOW_USERS": pwd.getpwuid(os.geteuid()).pw_name,
                "SYNC_ACL": "yes",
            }
        )
        ini = (
            f"[root]\nimportant_packages = {json.dumps(snapper['important_packages'])}\n"
            f"important_commands = {json.dumps(snapper['important_commands'])}\n"
        )
        ensure_file("/etc/snap-pac.ini", ini, owner="root:root")
        strategy.ensure_service("snapper-cleanup.timer")
        if snapper["timeline"]:
            strategy.ensure_service("snapper-timeline.timer")

    def _create_config(self) -> None:
        # create-config makes /.snapshots a subvolume of / and refuses when the
        # directory exists, as it does when a separate @snapshots is mounted
        # there from fstab: step aside, let it create (and drop) its own, remount.
        mounted = bool(output("findmnt", "-n", "/.snapshots"))
        with as_root():
            if mounted:
                run("umount", "/.snapshots")
                run("rmdir", "/.snapshots")
            run(*SNAPPER, "create-config", "/")
            if mounted:
                run("btrfs", "subvolume", "delete", "/.snapshots", stdout=subprocess.DEVNULL)
                run("mkdir", "/.snapshots")
                run("mount", "/.snapshots")
            run("chmod", "750", "/.snapshots")
        changed("snapper config root created")

    def _settings(self, want: dict[str, str]) -> None:
        # Readable as the user once ALLOW_USERS names them; before that the
        # answer is empty and every key is set, once.
        csv = output("snapper", "--machine-readable", "csv", "-c", "root", "get-config") or ""
        have = dict(line.split(",", 1) for line in csv.splitlines() if "," in line)
        differ = {key: value for key, value in want.items() if have.get(key) != value}
        if not differ:
            return
        with as_root():
            run(*SNAPPER, "set-config", *(f"{k}={v}" for k, v in differ.items()))
        for key, value in differ.items():
            changed(f"snapper {key} = {value}")

    @contextmanager
    def session(self, system):
        """The pair: snap-pac skips its own snapshots while the pre is taken
        on the first package change and the post when the apply ends."""
        # Not usable yet (first apply, no ALLOW_USERS), or a dry run: no pair.
        if engine.DRY_RUN or not output(*SNAPPER, "list"):
            yield
            return
        self._pre_number: str | None = None
        self._log_size = 0
        skip = os.environ.get("SNAP_PAC_SKIP")
        os.environ["SNAP_PAC_SKIP"] = "y"
        try:
            with platforms.watching(self._pre):
                yield
        finally:
            if skip is None:
                del os.environ["SNAP_PAC_SKIP"]
            else:
                os.environ["SNAP_PAC_SKIP"] = skip
            self._post()

    def _pre(self) -> None:
        if self._pre_number is not None:
            return
        self._pre_number = ""  # tried: a failure is not retried at every transaction
        log = engine.path(PACMAN_LOG)
        self._log_size = log.stat().st_size if log.exists() else 0
        try:
            done = run(*SNAPPER, "create", "-t", "pre", *NUMBERED, "-p", capture_output=True)
        except subprocess.CalledProcessError as e:
            notice(
                f"snapper pre snapshot failed ({(e.stderr or '').strip()}) — this apply has no pair"
            )
            return
        self._pre_number = done.stdout.strip()
        changed(f"snapper pre snapshot #{self._pre_number}")

    def _post(self) -> None:
        number = self._pre_number
        if not number:
            return
        important = self._important()
        try:
            if important:
                run(*SNAPPER, "modify", "-u", "important=yes", number)
            flags = ["-u", "important=yes"] if important else []
            run(*SNAPPER, "create", "-t", "post", "--pre-number", number, *NUMBERED, *flags)
        except subprocess.CalledProcessError:
            notice(f"snapper post snapshot for #{number} failed — the pre stays alone")
            return
        changed(f"snapper post snapshot for #{number}" + (" (important)" if important else ""))

    def _important(self) -> bool:
        """pacman.log since the pre names a package of important_packages:
        snap-pac's rule for a pair kept longer."""
        packages = self.cfg["features"]["snapper"]["important_packages"]
        log = engine.path(PACMAN_LOG)
        if not packages or not log.exists():
            return False
        with log.open("rb") as f:
            f.seek(self._log_size)
            since = f.read().decode(errors="replace")
        names = "|".join(map(re.escape, packages))
        return bool(re.search(rf"\] (installed|upgraded|reinstalled|removed) ({names}) ", since))

    class Arch:
        def packages(self):
            return ["snapper", "snap-pac"]


def swap_files_on_root() -> list[str]:
    """Active swap files on the root subvolume, which break its snapshots."""
    swaps = engine.path("/proc/swaps")
    lines = swaps.read_text().splitlines()[1:] if swaps.exists() else []
    files = [line.split()[0] for line in lines if line.split()[1:2] == ["file"]]
    return [f for f in files if output("findmnt", "-no", "TARGET", "-T", f) == "/"]
