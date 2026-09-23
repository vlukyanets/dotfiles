"""The helpers features are written with: the port of the old lib.sh.

Every check reads live state without root; every mutation goes through a
helper, `run` or `as_root`, and each of them does nothing on a dry run. That
is what keeps a clean apply silent and free of sudo prompts.
"""

import grp
import os
import platform
import pwd
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from time import sleep

# Set by `dotfiles apply --dry-run`: check and report, never mutate.
DRY_RUN = False
# Prefixed to every path a helper touches; tests point it at a temp dir.
SYSROOT = Path("/")
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


def _path(path) -> Path:
    return SYSROOT / str(path).lstrip("/")


def _writable(path: Path) -> bool:
    """The current user may create or replace PATH: the file itself, when it
    is one, and the nearest existing directory above it (install and ln
    replace the entry, a dangling symlink included)."""
    if path.is_file() and not path.is_symlink() and not os.access(path, os.W_OK):
        return False
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    return os.access(parent, os.W_OK)


def _owner(path: Path) -> str:
    """PATH's owner as user:group, numbers where a name is unknown."""
    st = path.stat()
    try:
        user = pwd.getpwuid(st.st_uid).pw_name
    except KeyError:
        user = str(st.st_uid)
    try:
        group = grp.getgrgid(st.st_gid).gr_name
    except KeyError:
        group = str(st.st_gid)
    return f"{user}:{group}"


def ensure_file(dst, content: str | bytes, mode: int = 0o644, owner: str | None = None) -> bool:
    """DST has CONTENT, MODE and OWNER ("user:group" or "user"). Compared
    without root; written with root only when the user cannot."""
    real = _path(dst)
    data = content.encode() if isinstance(content, str) else content
    user, _, group = (owner or "").partition(":")
    group = group or user
    try:
        current = real.read_bytes()
    except FileNotFoundError:
        current = None
    except OSError:  # unreadable without root: looks different every time
        current = b""
    if current is None:
        why = "missing"
    elif current != data:
        why = "content differs"
    elif stat.S_IMODE(real.stat().st_mode) != mode:
        why = f"mode {stat.S_IMODE(real.stat().st_mode):o}"
    elif owner and _owner(real) != f"{user}:{group}":
        why = f"owner {_owner(real)}"
    else:
        return False
    if not DRY_RUN:
        me = pwd.getpwuid(os.geteuid()).pw_name
        mutate = as_root if (owner and user != me) or not _writable(real) else run
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "content"
            src.write_bytes(data)
            opts = ["-o", user, "-g", group] if owner else []
            mutate("install", "-D", "-m", f"{mode:o}", *opts, str(src), str(real))
    changed(f"{dst} ({why})")
    return True


def ensure_symlink(target, link) -> bool:
    """LINK is a symlink to TARGET."""
    real = _path(link)
    try:
        if os.readlink(real) == str(target):
            return False
    except OSError:
        pass
    mutate = run if _writable(real) else as_root
    mutate("ln", "-sfn", str(target), str(real))
    changed(f"{link} -> {target}")
    return True


def ensure_line(file, regex: str, line: str) -> bool:
    """The first line of FILE matching REGEX becomes LINE, appended when
    nothing matches. FILE's mode and owner are kept."""
    real = _path(file)
    if not real.exists():
        return ensure_file(file, line + "\n")
    lines, done = [], False
    for old in real.read_text().splitlines():
        if not done and re.search(regex, old):
            old, done = line, True
        lines.append(old)
    if not done:
        lines.append(line)
    mode = stat.S_IMODE(real.stat().st_mode)
    return ensure_file(file, "\n".join(lines) + "\n", mode, _owner(real))


def ensure_service(unit: str, user: bool = False) -> bool:
    """UNIT is enabled and active; static units (no [Install]) are only
    started. USER: the user's systemd, no root."""
    scope = ["--user"] if user else []
    mutate = run if user else as_root
    enabled = output("systemctl", *scope, "is-enabled", unit) or ""
    active = output("systemctl", *scope, "is-active", unit) or ""
    if enabled in ("enabled", "static", "alias", "indirect"):
        if active == "active":
            return False
        mutate("systemctl", *scope, "start", unit)
    else:
        mutate("systemctl", *scope, "enable", "--now", unit)
    changed(f"{unit} enabled and started (was {enabled}/{active})")
    return True


def ensure_sysctl(key: str, value) -> bool:
    """KEY = VALUE persisted in /etc/sysctl.d and live."""
    edited = ensure_line(
        "/etc/sysctl.d/99-dotfiles.conf", f"^{re.escape(key)} *=", f"{key} = {value}"
    )
    if output("sysctl", "-n", key) == str(value):
        return edited
    as_root("sysctl", "-qw", f"{key}={value}")
    changed(f"sysctl {key} = {value}")
    return True


def ensure_gsetting(schema: str, key: str, value: str) -> bool:
    """VALUE in GVariant text form, e.g. "'prefer-dark'" with the inner
    quotes. Nothing without gsettings."""
    current = output("gsettings", "get", schema, key)
    if current is None or current == value:
        return False
    run("gsettings", "set", schema, key, value)
    changed(f"gsettings {schema} {key} = {value}")
    return True


def ensure_group_member(group: str) -> bool:
    """The current user is in GROUP. Read from the group database, not the
    session's groups (id -nG), which change only at the next login."""
    me = pwd.getpwuid(os.geteuid())
    try:
        entry = grp.getgrnam(group)
    except KeyError:
        die(f"group {group} does not exist")
    if me.pw_name in entry.gr_mem or me.pw_gid == entry.gr_gid:
        return False
    as_root("usermod", "-aG", group, me.pw_name)
    changed(f"added {me.pw_name} to group {group}")
    notice(f"added to group {group} — log out and back in for it to take effect")
    return True
