import grp
import os
import pwd
import re
import shlex
import stat
import subprocess
import sys
import tempfile
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from time import sleep


class Failed(Exception):
    """die(): this feature cannot go on."""


class Deferred(Exception):
    """defer(): a network step failed; the next apply retries."""


def die(msg: str):
    """Stop this feature with MSG: the error apply prints for it."""
    raise Failed(msg)


def defer(msg: str):
    """Stop this feature without failing it: the next apply retries."""
    raise Deferred(msg)


class Report:
    """What an apply prints: changes, warnings, and the notices replayed at its end."""

    def __init__(self):
        """Nothing printed yet, no notices."""
        self.printed = False  # a change or a warning; if not, apply says so
        self.notices: list[str] = []

    def warn(self, msg: str) -> None:
        """`warning: MSG` on stderr."""
        self.printed = True
        print(f"warning: {msg}", file=sys.stderr)

    def changed(self, msg: str) -> None:
        """A mutation: the only kind of line a clean apply never prints."""
        self.printed = True
        print(f"-> {msg}")

    def line(self, msg: str) -> None:
        """MSG as it is, counted as a change: a line render.deploy made."""
        self.printed = True
        print(msg)

    def notice(self, msg: str) -> None:
        """Print now and again at the end, where it is not lost under package output."""
        self.warn(msg)
        self.notices.append(msg)

    def flush(self) -> None:
        """Replay the notices, once."""
        if self.notices:
            print("\nNotices from this apply:")
            for msg in self.notices:
                print(f"    {msg}")
            self.notices.clear()


def _subprocess(argv: list[str], check: bool = False, **kwargs) -> subprocess.CompletedProcess:
    """The real way to run a command."""
    return subprocess.run(argv, check=check, text=True, **kwargs)


class Shell:
    """External commands: checks always, mutations only outside a dry run, root on request."""

    def __init__(self, dry_run: bool = False, execute=_subprocess):
        """EXECUTE runs every command; tests pass a fake."""
        self.dry_run = dry_run
        self.execute = execute
        self._root = False

    def output(self, *cmd: str, **kwargs) -> str | None:
        """CMD's stdout without its last newline, whatever it exits with; None if not found."""
        try:
            return self.execute(list(cmd), capture_output=True, **kwargs).stdout.removesuffix("\n")
        except FileNotFoundError:
            return None

    def run(self, *cmd: str, **kwargs) -> subprocess.CompletedProcess | None:
        """CMD run, failing on a non-zero exit; nothing in a dry run."""
        if self.dry_run:
            return None
        return self.execute([*(_sudo() if self._root else []), *cmd], check=True, **kwargs)

    @contextmanager
    def as_root(self):
        """Every run() inside goes through SUDO_CMD (sudo) unless already root."""
        was, self._root = self._root, True
        try:
            yield
        finally:
            self._root = was


def _sudo() -> list[str]:
    """The prefix that makes a command run as root."""
    if os.geteuid() == 0:
        return []
    return shlex.split(os.environ.get("SUDO_CMD", "sudo"))


def _writable(path: Path) -> bool:
    """Whether PATH can be written, or created, without root."""
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


class Files:
    """Files of the system, under SYSROOT: checked, and written only where they differ."""

    def __init__(self, shell: Shell, report: Report, sysroot: Path = Path("/")):
        """Writes through SHELL, changes into REPORT; tests point SYSROOT at a temp dir."""
        self.shell = shell
        self.report = report
        self.sysroot = Path(sysroot)

    def path(self, name) -> Path:
        """NAME, an absolute path on the system, under SYSROOT: where to read it."""
        return self.sysroot / str(name).lstrip("/")

    def ensure(
        self, dst, content: str | bytes, mode: int = 0o644, owner: str | None = None
    ) -> bool:
        """DST holds CONTENT with MODE and OWNER; root where needed; whether it changed."""
        real = self.path(dst)
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
        if not self.shell.dry_run:
            me = pwd.getpwuid(os.geteuid()).pw_name
            root = (owner and user != me) or not _writable(real)
            with tempfile.TemporaryDirectory() as tmp, self._root(root):
                src = Path(tmp) / "content"
                src.write_bytes(data)
                opts = ["-o", user, "-g", group] if owner else []
                self.shell.run("install", "-D", "-m", f"{mode:o}", *opts, str(src), str(real))
        self.report.changed(f"{dst} ({why})")
        return True

    def symlink(self, target, link) -> bool:
        """LINK is a symlink to TARGET."""
        real = self.path(link)
        try:
            if os.readlink(real) == str(target):
                return False
        except OSError:
            pass
        with self._root(not _writable(real)):
            self.shell.run("ln", "-sfn", str(target), str(real))
        self.report.changed(f"{link} -> {target}")
        return True

    def line(self, file, regex: str, line: str, before: str | None = None) -> bool:
        """The line of FILE matching REGEX is LINE, else LINE added before BEFORE or at the end."""
        real = self.path(file)
        if not real.exists():
            return self.ensure(file, line + "\n")
        lines, done = [], False
        for old in real.read_text().splitlines():
            if not done and re.search(regex, old):
                old, done = line, True
            lines.append(old)
        if not done:
            at = [i for i, old in enumerate(lines) if before and re.search(before, old)]
            lines.insert(at[0] if at else len(lines), line)
        mode = stat.S_IMODE(real.stat().st_mode)
        return self.ensure(file, "\n".join(lines) + "\n", mode, _owner(real))

    def _root(self, needed) -> AbstractContextManager:
        """The shell as root if NEEDED, else as it is."""
        return self.shell.as_root() if needed else nullcontext()


class Machine:
    """One apply's view of the system: its report, its shell, its files."""

    def __init__(self, dry_run: bool = False, sysroot: Path = Path("/"), execute=_subprocess):
        """A fresh report; commands through EXECUTE; files under SYSROOT."""
        self.report = Report()
        self.shell = Shell(dry_run, execute)
        self.files = Files(self.shell, self.report, sysroot)

    @property
    def dry_run(self) -> bool:
        """Check and report, never mutate."""
        return self.shell.dry_run

    @dry_run.setter
    def dry_run(self, value: bool) -> None:
        """Set by `dotfiles apply --dry-run`."""
        self.shell.dry_run = value

    def fresh(self, dry_run: bool) -> "Machine":
        """The same system and commands, with a new report and DRY_RUN: one per apply."""
        return Machine(dry_run, self.files.sysroot, self.shell.execute)

    @contextmanager
    def active(self):
        """This machine is the one the helpers below act on, inside the block."""
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)


# The system itself, for helpers called outside any active() block.
REAL = Machine()
_current: ContextVar[Machine | None] = ContextVar("machine", default=None)


def current() -> Machine:
    """The machine the helpers act on: an apply's, or REAL."""
    return _current.get() or REAL


# The helpers features call: each the same method of the current machine.


def warn(msg: str) -> None:
    """`warning: MSG` on stderr."""
    current().report.warn(msg)


def changed(msg: str) -> None:
    """A mutation: the only kind of line a clean apply never prints."""
    current().report.changed(msg)


def notice(msg: str) -> None:
    """Print now and again at the end, where it is not lost under package output."""
    current().report.notice(msg)


def print_notices() -> None:
    """Replay this apply's notices, once, at its end."""
    current().report.flush()


def output(*cmd: str, **kwargs) -> str | None:
    """CMD's stdout without its last newline, whatever it exits with; None if not found."""
    return current().shell.output(*cmd, **kwargs)


def run(*cmd: str, **kwargs) -> subprocess.CompletedProcess | None:
    """CMD run, failing on a non-zero exit; nothing in a dry run."""
    return current().shell.run(*cmd, **kwargs)


def as_root():
    """Every run() inside goes through SUDO_CMD (sudo) unless already root."""
    return current().shell.as_root()


def path(name) -> Path:
    """NAME, an absolute path on the system, under SYSROOT: where to read it."""
    return current().files.path(name)


def ensure_file(dst, content: str | bytes, mode: int = 0o644, owner: str | None = None) -> bool:
    """DST holds CONTENT with MODE and OWNER; root where needed; whether it changed."""
    return current().files.ensure(dst, content, mode, owner)


def ensure_symlink(target, link) -> bool:
    """LINK is a symlink to TARGET."""
    return current().files.symlink(target, link)


def ensure_line(file, regex: str, line: str, before: str | None = None) -> bool:
    """The line of FILE matching REGEX is LINE, else LINE added before BEFORE or at the end."""
    return current().files.line(file, regex, line, before)


@dataclass(frozen=True)
class RetryPolicy:
    """How often and how long apart retrying() tries again."""

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
    """One try of retrying(): a failure it swallows makes the loop go again."""

    def __init__(self, policy: RetryPolicy, number: int):
        """Try NUMBER of POLICY."""
        self.policy = policy
        self.number = number
        self.failed = False

    def __enter__(self):
        """The attempt itself."""
        return self

    def __exit__(self, kind, error, traceback) -> bool:
        """Swallow a retryable error, warn and wait, unless it is the last attempt."""
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
    """Attempts to run `with attempt:` until one succeeds; the last failure propagates."""
    for number in range(1, policy.attempts + 1):
        attempt = Attempt(policy, number)
        yield attempt
        if not attempt.failed:
            return


def network(*cmd: str, failure: str, **kwargs) -> None:
    """CMD run, retried; still failing, the feature is deferred with FAILURE."""
    kwargs.setdefault("stdout", subprocess.DEVNULL)
    try:
        for attempt in retrying():
            with attempt:
                run(*cmd, **kwargs)
    except subprocess.CalledProcessError:
        defer(failure)
