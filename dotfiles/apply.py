import importlib
import pkgutil
import shlex
import subprocess
import sys
import sysconfig
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import NamedTuple

from dotfiles import config, engine, render
from dotfiles.config import ROOT, ConfigError, MissingKey
from dotfiles.feature import Feature
from dotfiles.platforms import discovery
from dotfiles.platforms.operating_system import Platform

PACKAGE = "dotfiles.features"


class Step(NamedTuple):
    """One enabled feature on this platform, with what it installs and needs."""

    name: str  # the module's name, and the feature's in the schema
    feature: Feature
    strategy: Platform
    packages: frozenset[str]
    replaces: frozenset[str]
    requires: frozenset[str] = frozenset()  # features that must be on, and run first


def features(cfg: dict, package: str = PACKAGE) -> list[tuple[str, Feature]]:
    """(name, instance) of every feature module whose feature CFG does not disable."""
    found = []
    for info in sorted(pkgutil.iter_modules(importlib.import_module(package).__path__)):
        name = info.name
        if name in cfg["features"] and not cfg["features"][name]["enabled"]:
            continue
        module = importlib.import_module(f"{package}.{name}")
        classes = [c for c in discovery.classes(module) if issubclass(c, Feature)]
        if len(classes) != 1:
            raise ConfigError(f"{package}.{name}: defines {len(classes)} features, not one")
        found.append((name, classes[0](cfg)))
    return found


def steps(cfg: dict, system: Platform, package: str = PACKAGE) -> list[Step]:
    """A Step per feature that runs on SYSTEM; fails if a requirement is unmet or cyclic."""
    found = []
    for name, feature in features(cfg, package):
        strategy = feature.strategy(system)
        if strategy is not None:  # none: the feature does not apply here
            packages, replaces = frozenset(strategy.packages()), frozenset(strategy.replaces())
            requires = frozenset(strategy.requires())
            found.append(Step(name, feature, strategy, packages, replaces, requires))
    requires = {step.name: step.requires for step in found}
    if problems := unmet(cfg, requires) + circles(requires):
        raise ConfigError("; ".join(problems))
    return found


def unmet(cfg: dict, requires: dict[str, frozenset[str]]) -> list[str]:
    """What each feature REQUIRES that CFG does not enable, one line each."""
    problems = []
    for feature, names in sorted(requires.items()):
        for name in sorted(names):
            if name not in cfg["features"]:
                problems.append(f"{feature}: requires {name}, which is not a feature")
            elif not cfg["features"][name]["enabled"]:
                problems.append(f"{feature}: requires features.{name}.enabled = true")
    return problems


def cycles(edges: dict[str, frozenset[str] | list[str]]) -> list[list[str]]:
    """Every cycle of EDGES (name -> names it needs), each once, from its smallest name."""
    found: dict[frozenset[str], list[str]] = {}
    done: set[str] = set()

    def visit(path: list[str]) -> None:
        """Walk on from the last name of PATH, recording each cycle back into it."""
        for name in sorted(edges.get(path[-1], ())):
            if name in path:
                cycle = path[path.index(name) :]
                first = cycle.index(min(cycle))
                found.setdefault(frozenset(cycle), cycle[first:] + cycle[:first])
            elif name not in done and name in edges:
                visit([*path, name])
        done.add(path[-1])

    for name in sorted(edges):
        if name not in done:
            visit([name])
    return sorted(found.values())


def circle(cycle: list[str]) -> str:
    """CYCLE as `a → b → a`."""
    return " → ".join([*cycle, cycle[0]])


def circles(requires: dict[str, frozenset[str]]) -> list[str]:
    """Each cycle of REQUIRES, one line each: none of its features can run first."""
    return [f"{circle(c)}: each requires the next, so none can run first" for c in cycles(requires)]


def requirements(
    cfg: dict, package: str = PACKAGE, platform_package: str = discovery.PACKAGE
) -> None:
    """Fail if a feature's requires() is unmet or cyclic on any platform: for check."""
    found = [(n, f) for n, f in features(cfg, package) if n in cfg["features"]]
    problems: list[str] = []
    for system in discovery.every(cfg, platform_package):
        strategies = {name: feature.strategy(system) for name, feature in found}
        requires = {n: frozenset(s.requires()) for n, s in strategies.items() if s is not None}
        problems += [p for p in unmet(cfg, requires) + circles(requires) if p not in problems]
    if problems:
        raise ConfigError("; ".join(problems))


def order(steps: list[Step], depends: dict[str, set[str]]) -> list[tuple[Step, list[str]]]:
    """STEPS in run order, each with the features it runs after (packages and requires)."""
    owners: dict[str, set[str]] = {}
    for step in steps:
        for pkg in step.packages:
            owners.setdefault(pkg, set()).add(step.name)
    names = {step.name for step in steps}
    after = {
        step.name: sorted(
            {
                owner
                for pkg in step.packages
                for dep in depends.get(pkg, ())
                if dep not in step.packages
                for owner in owners.get(dep, ())
            }
            | (step.requires & names)
        )
        for step in steps
    }
    todo = sorted(steps)
    done: list[tuple[Step, list[str]]] = []
    ran: set[str] = set()
    while todo:
        ready = [step for step in todo if ran.issuperset(after[step.name])]
        step = (ready or todo)[0]
        todo.remove(step)
        ran.add(step.name)
        done.append((step, after[step.name]))
    return done


def _deploy(host: str, root: Path, cfg: dict) -> None:
    """The dotfiles into $HOME, printing each change."""
    machine = engine.current()
    for line in render.deploy(host, root, dry_run=machine.dry_run, cfg=cfg):
        machine.report.line(line)


def _where(e: BaseException) -> str:
    """The innermost line of our own code that raised E: file:line and the line itself."""
    libs = [sysconfig.get_paths()[k] for k in ("stdlib", "platstdlib", "purelib", "platlib")]
    skip = (*libs, engine.__file__, config.__file__)
    frames = [f for f in traceback.extract_tb(e.__traceback__) if not f.filename.startswith(skip)]
    if not frames:
        return ""
    frame = frames[-1]
    path = Path(frame.filename)
    shown = path.relative_to(ROOT) if path.is_relative_to(ROOT) else path
    return f", at {shown}:{frame.lineno}: {frame.line}"


def describe(e: BaseException) -> str:
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
    text = describe(msg) if isinstance(msg, BaseException) else msg
    print(f"error: {name}: {text}", file=sys.stderr)


class Apply:
    """One apply on SYSTEM: setup, packages, dotfiles, then the features in order."""

    def __init__(self, host: str, root: Path, cfg: dict, system: Platform, found: list[Step]):
        """The run of FOUND on SYSTEM for HOST; nothing failed yet."""
        self.host, self.root, self.cfg = host, root, cfg
        self.system = system
        self.steps = found
        self.failed: set[str] = set()  # phases and features, by name
        self.wanted = sorted(set().union(*(step.packages for step in found)))
        self.unavailable: set[str] = set()  # wanted, and still missing after the install

    def run(self) -> int:
        """Every phase in turn; 1 if anything failed."""
        ready = self._setup()
        self._packages(ready)
        with self._guard("dotfiles"):
            _deploy(self.host, self.root, self.cfg)
        self._features()
        if not engine.current().report.printed and not self.failed:
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
        engine.changed(f"packages: {' '.join(missing)} (missing)")
        if engine.current().dry_run:
            return  # nothing installed, so nothing failed to be
        if ready:
            replaced = sorted(set().union(*(step.replaces for step in self.steps)))
            with self._guard("packages"):
                manager.install(missing, replaced)
        self.unavailable = set(manager.missing(self.wanted))

    def _features(self) -> None:
        """Each feature in order, unless what it builds on failed."""
        graph = self.system.manager.depends(self.wanted) if self.wanted else {}
        ordered = order(self.steps, graph)
        for cycle in cycles({step.name: after for step, after in ordered}):
            self.failed.update(cycle)  # features are cut so they never need each other
            _error(", ".join(cycle), f"not run, they need each other: {circle(cycle)}")
        for step, after in ordered:
            if step.name in self.failed:
                continue
            if why := self._blocked(step, after):
                self._fail(step.name, f"not run, {why}")
                continue
            with self._guard(step.name):
                try:
                    step.feature.apply(step.strategy)
                except engine.Deferred as e:
                    engine.notice(f"{e} (network?) — the next apply retries")

    def _blocked(self, step: Step, after: list[str]) -> str | None:
        """Why STEP cannot run: its packages missing, or what it runs after failed."""
        if gone := sorted(step.packages & self.unavailable):
            return f"packages missing: {' '.join(gone)}"
        if blocked := [name for name in after if name in self.failed]:
            return f"{', '.join(blocked)} failed"
        return None


def apply(
    host: str,
    root: Path = ROOT,
    dry_run: bool = False,
    package: str = PACKAGE,
    platform_package: str = discovery.PACKAGE,
    cfg: dict | None = None,
) -> int:
    """Every enabled feature and the dotfiles on this machine; 1 if anything failed."""
    cfg = config.resolve(host, root) if cfg is None else cfg
    with engine.current().fresh(dry_run).active() as machine:
        try:
            system = discovery.detect(cfg, platform_package)
            return Apply(host, root, cfg, system, steps(cfg, system, package)).run()
        finally:  # after a failure and on Ctrl-C too
            machine.report.flush()
