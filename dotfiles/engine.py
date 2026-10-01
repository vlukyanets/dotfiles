import atexit
import grp
import os
import pwd
import re
import shlex
import socket
import stat
import subprocess
import sys
import tempfile
from contextlib import AbstractContextManager, contextmanager, nullcontext
from contextvars import ContextVar
from multiprocessing.connection import Connection
from pathlib import Path


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

    def __init__(self, dry_run: bool = False, execute=_subprocess, root=None):
        """EXECUTE runs every command, ROOT (SUDO argv, **kwargs) every root one; tests fake both."""
        self.dry_run = dry_run
        self.execute = execute
        self.root = root or _Root()
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
        if self._root and (sudo := _sudo()):
            return self.root(sudo, list(cmd), check=True, **kwargs)
        return self.execute(list(cmd), check=True, **kwargs)

    @contextmanager
    def as_root(self):
        """Every run() inside goes through SUDO_CMD (sudo) unless already root."""
        was, self._root = self._root, True
        try:
            yield
        finally:
            self._root = was


class _Root:
    """One root process, started by the first command: SUDO_CMD asks once, for all of them."""

    def __init__(self):
        """Nothing started yet."""
        self._conn: Connection | None = None

    def __call__(self, sudo: list[str], argv: list[str], **kwargs) -> subprocess.CompletedProcess:
        """ARGV run as root with subprocess.run KWARGS; its errors raised here."""
        if self._conn is None:
            self._start(sudo)
        self._conn.send((argv, kwargs))
        result = self._conn.recv()
        if isinstance(result, BaseException):
            raise result
        return result

    def _start(self, sudo: list[str]) -> None:
        """SUDO + dotfiles/root.py started and connected; CalledProcessError if it exits."""
        self._dir = tempfile.TemporaryDirectory()
        address = str(Path(self._dir.name) / "root")
        listener = socket.socket(socket.AF_UNIX)
        listener.bind(address)
        listener.listen(1)
        listener.settimeout(0.2)
        argv = [*sudo, sys.executable, "-I", str(Path(__file__).with_name("root.py")), address]
        # stdin a pipe, closed at once: sudo's use_pty keeps the terminal in raw mode
        # while stdin is the terminal, and every line we print steps down the screen.
        # /dev/null would not do: sudo tells a pipe apart, not any non-terminal.
        self._process = subprocess.Popen(argv, stdin=subprocess.PIPE)
        self._process.stdin.close()
        while True:  # sudo may be asking for the password
            try:
                sock, _ = listener.accept()
                break
            except TimeoutError:
                if self._process.poll() is not None:
                    raise subprocess.CalledProcessError(self._process.returncode, argv) from None
        listener.close()
        sock.setblocking(True)
        self._conn = Connection(sock.detach())
        atexit.register(self._close)

    def _close(self) -> None:
        """Hang up; the root process exits and sudo gives the terminal back."""
        self._conn.close()
        self._process.wait()
        self._dir.cleanup()


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


def differs(real: Path, data: bytes, mode: int, owner: str | None = None) -> str | None:
    """Why REAL is not DATA with MODE and OWNER (missing, content, mode, owner); None if it is."""
    try:
        current = real.read_bytes()
    except FileNotFoundError:
        return "missing"
    except OSError:  # unreadable without root: looks different every time
        return "content differs"
    if current != data:
        return "content differs"
    if stat.S_IMODE(real.stat().st_mode) != mode:
        return f"mode {stat.S_IMODE(real.stat().st_mode):o}"
    if owner and _owner(real) != owner:
        return f"owner {_owner(real)}"
    return None


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
        why = differs(real, data, mode, owner and f"{user}:{group}")
        if why is None:
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
        try:
            text = real.read_text()
        except PermissionError:
            die(f"{file}: not readable without root; features keep root files world-readable")
        lines, done = [], False
        for old in text.splitlines():
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

    def __init__(
        self, dry_run: bool = False, sysroot: Path = Path("/"), execute=_subprocess, root=None
    ):
        """A fresh report; commands through EXECUTE, root ones through ROOT; files under SYSROOT."""
        self.report = Report()
        self.shell = Shell(dry_run, execute, root)
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
        return Machine(dry_run, self.files.sysroot, self.shell.execute, self.shell.root)

    @contextmanager
    def active(self):
        """This machine is the one current() gives entry points, inside the block."""
        token = _current.set(self)
        try:
            yield self
        finally:
            _current.reset(token)


# The system itself, for an entry point called outside any active() block.
_REAL = Machine()
_current: ContextVar[Machine | None] = ContextVar("machine", default=None)


def current() -> Machine:
    """The machine an entry point builds on: the active one (a test's), or REAL."""
    return _current.get() or _REAL
