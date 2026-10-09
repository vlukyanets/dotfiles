import shlex
import socket
import subprocess
import sys
import sysconfig
import traceback
from contextlib import contextmanager
from pathlib import Path

from dotfiles import config, engine, feature, retry
from dotfiles.config import MissingKey
from dotfiles.errors import ConfigError
from dotfiles.layout import Layout, local_config
from dotfiles.plan import Step, circle, cycles, order, requirements, steps
from dotfiles.platforms import discovery
from dotfiles.platforms.operating_system import OperatingSystem


def _where(e: BaseException) -> str:
    """The innermost line of our own code that raised E: file:line and the line itself."""
    libs = [sysconfig.get_paths()[k] for k in ("stdlib", "platstdlib", "purelib", "platlib")]
    skip = (*libs, engine.__file__, retry.__file__, config.__file__)
    frames = [f for f in traceback.extract_tb(e.__traceback__) if not f.filename.startswith(skip)]
    if not frames:
        return ""
    frame = frames[-1]
    path = Path(frame.filename)
    shown = path.relative_to(Layout.root) if path.is_relative_to(Layout.root) else path
    return f", at {shown}:{frame.lineno}: {frame.line}"


def _describe(e: BaseException) -> str:
    """E as one line: die() and ConfigError as written, anything else with what and where."""
    if isinstance(e, (engine.Failed, ConfigError)):
        return str(e)
    if isinstance(e, MissingKey):
        return f"{e}{_where(e)}"
    if isinstance(e, subprocess.CalledProcessError):
        cmd = shlex.join(map(str, e.cmd)) if isinstance(e.cmd, list) else str(e.cmd)
        return f"`{cmd}` failed with exit status {e.returncode}{_where(e)}"
    detail = f" ({e})" if str(e) else ""
    return f"unexpected {type(e).__name__}{detail}{_where(e)}"


def _error(name: str, msg) -> None:
    """`error: NAME: …` on stderr; an exception is described by describe()."""
    text = _describe(msg) if isinstance(msg, BaseException) else msg
    print(f"error: {name}: {text}", file=sys.stderr)


class Apply:
    """One apply on SYSTEM: setup, packages, then the features in order."""

    def __init__(
        self, host: str, root: Path, cfg: dict, system: OperatingSystem, found: list[Step]
    ):
        """The run of FOUND on SYSTEM for HOST; nothing failed yet."""
        self.host, self.root, self.cfg = host, root, cfg
        self.system = system
        self.report = system.report
        self.steps = found
        self.failed: set[str] = set()  # phases and features, by name
        self.wanted = sorted(set().union(*(step.packages for step in found)))
        self.unavailable: set[str] = set()  # wanted, and still missing after the install
        self.pending: set[str] = set()  # missing, left so by a dry run
        # Not in the repositories: each built at its feature's turn, after what it requires.
        self.later: set[str] = set()
        self.waiting: set[str] = set()  # features a dry run cannot check before their packages

    def run(self) -> int:
        """Every phase in turn; 1 if anything failed."""
        ready = self._setup()
        self._early()
        self._packages(ready)
        self._features()
        if not self.report.printed and not self.failed:
            print("nothing to change")
        return 1 if self.failed else 0

    @contextmanager
    def _guard(self, name: str):
        """Any exception inside fails NAME alone: printed, recorded, and the apply goes on."""
        try:
            yield
        except Exception as e:  # noqa: BLE001 — a failure ends only NAME
            self._fail(name, e)

    def _fail(self, name: str, msg) -> None:
        """NAME failed with MSG, a text or an exception."""
        self.failed.add(name)
        _error(name, msg)

    def _setup(self) -> bool:
        """The package manager made ready; whether it is."""
        with self._guard("platform"):
            self.system.manager.setup()
            return True
        return False

    def _packages(self, ready: bool) -> None:
        """The missing packages installed in one go, what they replace removed first."""
        manager = self.system.manager
        missing = manager.missing(self.wanted)
        if not missing:
            return
        self.report.changed(f"packages: {' '.join(missing)} (missing)")
        if self.system.shell.dry_run:
            self.pending = set(missing)  # nothing installed, so nothing failed to be
            return
        if ready:
            replaced = sorted(set().union(*(step.replaces for step in self.steps)))
            with self._guard("packages"):
                self.later = set(manager.install(missing, replaced))
        self.unavailable = set(manager.missing(self.wanted)) - self.later

    def _features(self) -> None:
        """Each feature in order, unless what it builds on failed."""
        manager = self.system.manager
        graph = manager.depends(self.wanted) if self.wanted else {}
        provides = manager.provides(self.wanted) if self.wanted else {}
        ordered = order(self.steps, graph, provides)
        for cycle in cycles({step.name: after for step, after in ordered}):
            self.failed.update(cycle)  # features are cut so they never need each other
            _error(", ".join(cycle), f"not run, they need each other: {circle(cycle)}")
        for step, after in ordered:
            if not step.feature.before_packages:  # those ran before the install
                self._run(step, after)

    def _early(self) -> None:
        """The features before packages, ordered by their requirements alone.

        Not by the package graph: depends() caches for the apply, and would keep a
        package of a repository this phase adds (steam, of multilib) as needing nothing.
        """
        for step, after in order([s for s in self.steps if s.feature.before_packages], {}):
            self._run(step, after)

    def _run(self, step: Step, after: list[str]) -> None:
        """STEP, unless it failed already or what it runs AFTER did."""
        if step.name in self.failed:
            return
        if why := self._blocked(step, after):
            self._fail(step.name, f"not run, {why}")
            return
        if step.packages & self.pending or self.waiting.intersection(after):
            self.waiting.add(step.name)  # its checks would only see what is not there yet
            self.report.changed(f"{step.name} (after its packages)")
            return
        with self._guard(step.name):
            if later := sorted(step.packages & self.later):
                self.system.manager.build(later)
                self.later -= set(later)
            try:
                step.feature.apply()
            except engine.Deferred as e:
                self.report.notice(f"{e} (network?) — the next apply retries")

    def _blocked(self, step: Step, after: list[str]) -> str | None:
        """Why STEP cannot run: its packages missing, or what it runs after failed."""
        if gone := sorted(step.packages & self.unavailable):
            return f"packages missing: {' '.join(gone)}"
        if blocked := [name for name in after if name in self.failed]:
            return f"{', '.join(blocked)} failed"
        return None


def check(root: Path = Layout.root, source: Path | None = None) -> dict[str, str | None]:
    """Every host, and this machine's config, resolved and its requirements met: host -> error."""
    checks = feature.checks()
    results = config.check(root, source, checks=checks)
    local = local_config()
    if local.exists():
        results["local"] = None
    for host, error in results.items():
        if error is None:
            try:
                if host == "local":
                    cfg = config.resolve(socket.gethostname(), root, local, checks=checks)
                else:
                    cfg = config.resolve(host, root, source=source, checks=checks)
                requirements(cfg)
            except ConfigError as e:
                results[host] = str(e)
    return results


def apply(
    host: str,
    root: Path = Layout.root,
    dry_run: bool = False,
    cfg: dict | None = None,
) -> int:
    """Every enabled feature on this machine; 1 if anything failed."""
    cfg = config.resolve(host, root, checks=feature.checks()) if cfg is None else cfg
    machine = engine.current().fresh(dry_run)
    try:
        system = discovery.detect(machine)
        return Apply(host, root, cfg, system, steps(cfg, system)).run()
    finally:  # after a failure and on Ctrl-C too
        machine.report.flush()
