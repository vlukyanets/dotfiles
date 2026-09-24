"""The helpers features are written with.

Every check reads live state without root; every mutation goes through a
helper or `run` (as root inside `with as_root():`), and each of them does
nothing on a dry run. That is what keeps a clean apply silent and free of
sudo prompts.
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
from contextlib import contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
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


def output(*cmd: str, **kwargs) -> str | None:
    """CMD's stdout without the trailing newline, whatever its exit status
    (systemctl is-enabled says "disabled" and exits 1); None when CMD is not
    installed. For checks only."""
    try:
        return _run(list(cmd), capture_output=True, **kwargs).stdout.removesuffix("\n")
    except FileNotFoundError:
        return None


# Set inside `with as_root():`; read by run().
_root: ContextVar[bool] = ContextVar("root", default=False)


@contextmanager
def as_root():
    """Every run() in the block runs as root, through sudo, which prompts on
    its own when its timestamp has expired. Checks (output()) never do."""
    token = _root.set(True)
    try:
        yield
    finally:
        _root.reset(token)


def run(*cmd: str, **kwargs) -> None:
    """A mutation, as the user or inside as_root() as root; must succeed.
    Nothing on a dry run."""
    if not DRY_RUN:
        _run([*(_sudo() if _root.get() else []), *cmd], check=True, **kwargs)


def _sudo() -> list[str]:
    if os.geteuid() == 0:
        return []
    sudo = shlex.split(os.environ.get("SUDO_CMD", "sudo"))
    # During a snapper-wrapped apply the pacman hook needs these two; a
    # sudoers rule matching ALL implies SETENV.
    if sudo and os.environ.get("DOTFILES_SNAPPER_STATE"):
        sudo.append("--preserve-env=SNAP_PAC_SKIP,DOTFILES_SNAPPER_STATE")
    return sudo


@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3  # in total, the first one included
    delay: float = 10  # seconds before the second attempt
    backoff: float = 2  # each next delay is the previous one times this
    max_delay: float = 60  # no single wait longer than this
    retry_on: tuple[type[Exception], ...] = (subprocess.CalledProcessError, OSError)

    def wait(self, attempt: int) -> float:
        """Seconds to wait after failed attempt number ATTEMPT."""
        return min(self.delay * self.backoff ** (attempt - 1), self.max_delay)


# For anything that goes to the network: 3 attempts, 10 s then 20 s apart.
NETWORK = RetryPolicy()


class Attempt:
    """One pass of a retrying() loop: `with attempt:` swallows a failure
    that POLICY retries, unless it is the last attempt."""

    def __init__(self, policy: RetryPolicy, number: int):
        self.policy = policy
        self.number = number
        self.failed = False

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback) -> bool:
        if error is None or not isinstance(error, self.policy.retry_on):
            return False
        if self.number == self.policy.attempts:
            return False
        what = error.cmd if isinstance(error, subprocess.CalledProcessError) else None
        what = " ".join(map(str, what)) if isinstance(what, list) else str(error)
        wait = self.policy.wait(self.number)
        warn(f"{what} failed (attempt {self.number}/{self.policy.attempts}), retrying in {wait:g}s")
        sleep(wait)
        self.failed = True
        return True


def retrying(policy: RetryPolicy = NETWORK):
    """`for attempt in retrying(): with attempt: ...`: the block again, from
    the top, until it succeeds or POLICY's attempts run out; the last
    failure propagates. A with block runs once, hence the loop."""
    for number in range(1, policy.attempts + 1):
        attempt = Attempt(policy, number)
        yield attempt
        if not attempt.failed:
            return


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
        root = (owner and user != me) or not _writable(real)
        with tempfile.TemporaryDirectory() as tmp, as_root() if root else nullcontext():
            src = Path(tmp) / "content"
            src.write_bytes(data)
            opts = ["-o", user, "-g", group] if owner else []
            run("install", "-D", "-m", f"{mode:o}", *opts, str(src), str(real))
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
    with nullcontext() if _writable(real) else as_root():
        run("ln", "-sfn", str(target), str(real))
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
