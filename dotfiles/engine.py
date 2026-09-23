"""The helpers features are written with: the port of the old lib.sh.

Every check reads live state without root; every mutation goes through a
helper, `run` or `as_root`, and each of them does nothing on a dry run. That
is what keeps a clean apply silent and free of sudo prompts.
"""

import os
import platform
import shlex
import subprocess
import sys
from time import sleep

# Set by `dotfiles apply --dry-run`: check and report, never mutate.
DRY_RUN = False
# Notices of this apply, replayed at the end by print_notices().
notices: list[str] = []


class Failed(Exception):
    """die(): this feature cannot go on."""


class Skip(Exception):
    """os_guard(): this feature does not apply to this machine."""


class Deferred(Exception):
    """defer(): a network step failed; the next apply retries."""


def warn(msg: str) -> None:
    print(f"warning: {msg}", file=sys.stderr)


def die(msg: str):
    raise Failed(msg)


def changed(msg: str) -> None:
    """A mutation: the only kind of line a clean apply never prints."""
    print(f"-> {msg}")


def notice(msg: str) -> None:
    """Print now and again at the end, where it is not lost under package output."""
    warn(msg)
    notices.append(msg)


def print_notices() -> None:
    if notices:
        print("\nNotices from this apply:")
        for msg in notices:
            print(f"    {msg}")
        notices.clear()


def defer(msg: str):
    """A network step failed and nothing later needs it: the rest of this
    feature is left to the next apply, whose checks find the state still missing."""
    raise Deferred(msg)


def os_guard(*names: str) -> None:
    """End the feature silently unless this machine is one of NAMES: an OS
    (linux, darwin), a distro id (arch) or a family from ID_LIKE (debian)."""
    try:
        release = platform.freedesktop_os_release()
    except OSError:
        release = {}
    ids = {sys.platform, release.get("ID", ""), *release.get("ID_LIKE", "").split()}
    if not ids & set(names):
        raise Skip


def _run(argv: list[str], check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """Every external command goes through here, so tests can replace it."""
    return subprocess.run(argv, check=check, text=True, **kwargs)


def output(*cmd: str) -> str | None:
    """CMD's stdout without the trailing newline, whatever its exit status
    (systemctl is-enabled says "disabled" and exits 1); None when CMD is not
    installed. For checks only."""
    try:
        return _run(list(cmd), capture_output=True).stdout.removesuffix("\n")
    except FileNotFoundError:
        return None


def run(*cmd: str) -> None:
    """A mutation as the current user; must succeed. Nothing on a dry run."""
    if not DRY_RUN:
        _run(list(cmd), check=True)


def _sudo() -> list[str]:
    if os.geteuid() == 0:
        return []
    sudo = shlex.split(os.environ.get("SUDO_CMD", "sudo"))
    # During a snapper-wrapped apply the pacman hook needs these two; a
    # sudoers rule matching ALL implies SETENV.
    if sudo and os.environ.get("DOTFILES_SNAPPER_STATE"):
        sudo.append("--preserve-env=SNAP_PAC_SKIP,DOTFILES_SNAPPER_STATE")
    return sudo


def as_root(*cmd: str) -> None:
    """A mutation as root, through sudo, which prompts on its own when its
    timestamp has expired; must succeed. Nothing on a dry run."""
    if not DRY_RUN:
        _run([*_sudo(), *cmd], check=True)


def retry(fn, *args) -> bool:
    """fn(*args) up to three times, 10 s and 20 s apart, for anything that
    goes to the network. False when the last attempt fails too."""
    attempt = 1
    while True:
        try:
            fn(*args)
            return True
        except (subprocess.CalledProcessError, OSError):
            if attempt == 3:
                return False
            what = " ".join(map(str, args))
            warn(f"{what} failed (attempt {attempt}/3), retrying in {attempt * 10}s")
            sleep(attempt * 10)
            attempt += 1
