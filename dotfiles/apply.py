"""dotfiles apply: the platform, the packages of every feature at once, the
dotfiles, then the features in the order their packages and their declared
requirements need each other, and the notices at the end."""

import importlib
import pkgutil
import sys
from contextlib import ExitStack
from pathlib import Path
from typing import NamedTuple

from dotfiles import config, engine, platforms, render
from dotfiles.config import ROOT, ConfigError
from dotfiles.feature import Feature
from dotfiles.platforms import Platform

PACKAGE = "dotfiles.features"


class Step(NamedTuple):
    name: str  # the module's name, and the feature's in the schema
    feature: Feature
    strategy: Platform
    packages: frozenset[str]
    replaces: frozenset[str]
    requires: frozenset[str] = frozenset()  # features that must be on, and run first


def features(cfg: dict, package: str = PACKAGE) -> list[tuple[str, Feature]]:
    """The features of PACKAGE that CFG does not switch off, by name. A
    module whose name is not a feature in the schema is not switched by
    one: it always runs and reads its flags itself."""
    found = []
    for info in sorted(pkgutil.iter_modules(importlib.import_module(package).__path__)):
        name = info.name
        if name in cfg["features"] and not cfg["features"][name]["enabled"]:
            continue
        module = importlib.import_module(f"{package}.{name}")
        classes = [c for c in platforms.classes(module) if issubclass(c, Feature)]
        if len(classes) != 1:
            raise ConfigError(f"{package}.{name}: defines {len(classes)} features, not one")
        found.append((name, classes[0](cfg)))
    return found


def steps(cfg: dict, system: Platform, package: str = PACKAGE) -> list[Step]:
    """The features of PACKAGE that are enabled and have a strategy for
    SYSTEM, by name; a ConfigError when one requires a feature that is off."""
    found = []
    for name, feature in features(cfg, package):
        strategy = feature.strategy(system)
        if strategy is not None:  # none: the feature does not apply here
            packages, replaces = frozenset(strategy.packages()), frozenset(strategy.replaces())
            requires = frozenset(strategy.requires())
            found.append(Step(name, feature, strategy, packages, replaces, requires))
    if problems := unmet(cfg, {step.name: step.requires for step in found}):
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


def requirements(
    cfg: dict, package: str = PACKAGE, platform_package: str = platforms.PACKAGE
) -> None:
    """The requirements of what CFG enables, on every platform: a ConfigError
    naming each one left off. Only requires() is asked, so nothing is read
    from this machine; modules the schema does not know are not checked."""
    found = [(n, f) for n, f in features(cfg, package) if n in cfg["features"]]
    problems: list[str] = []
    for system in platforms.every(cfg, platform_package):
        strategies = {name: feature.strategy(system) for name, feature in found}
        requires = {n: frozenset(s.requires()) for n, s in strategies.items() if s is not None}
        problems += [p for p in unmet(cfg, requires) if p not in problems]
    if problems:
        raise ConfigError("; ".join(problems))


def order(steps: list[Step], depends: dict[str, set[str]]) -> list[tuple[Step, list[str]]]:
    """STEPS in running order, each with the names of the steps it runs
    after: B after A when B requires A, or when a package of B needs a
    package that A has and B does not. Ties go by name; a cycle is broken by
    name too."""
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
    for line in render.deploy(host, root, dry_run=engine.DRY_RUN, cfg=cfg):
        engine.printed = True
        print(line)


def _error(name: str, msg) -> None:
    print(f"error: {name}: {msg}", file=sys.stderr)


def _phases(
    host: str, root: Path, cfg: dict, system: Platform, found: list[Step], failed: set[str]
) -> None:
    """Setup, packages, dotfiles, features; FAILED collects what failed."""
    wanted = sorted(set().union(*(step.packages for step in found)))
    replaced = sorted(set().union(*(step.replaces for step in found)))

    try:
        system.setup()
        ready = True
    except Exception as e:  # noqa: BLE001 — what needs no install still runs
        failed.add("platform")
        _error("platform", e)
        ready = False
    missing = system.missing(wanted)
    if missing:
        engine.changed(f"packages: {' '.join(missing)} (missing)")
        try:
            if ready and not engine.DRY_RUN:
                system.install(missing, replaced)
        except Exception as e:  # noqa: BLE001 — the features without them still run
            failed.add("packages")
            _error("packages", e)
        if not engine.DRY_RUN:
            missing = system.missing(wanted)

    try:
        _deploy(host, root, cfg)
    except Exception as e:  # noqa: BLE001 — the features still run
        failed.add("dotfiles")
        _error("dotfiles", e)

    for step, after in order(found, system.depends(wanted) if wanted else {}):
        if not engine.DRY_RUN and step.packages & set(missing):
            failed.add(step.name)
            gone = " ".join(sorted(step.packages & set(missing)))
            _error(step.name, f"not run, packages missing: {gone}")
            continue
        blocked = [name for name in after if name in failed]
        if blocked:
            failed.add(step.name)
            _error(step.name, f"not run, {', '.join(blocked)} failed")
            continue
        try:
            step.feature.apply(step.strategy)
        except engine.Deferred as e:
            engine.notice(f"{e} (network?) — the next apply retries")
        except Exception as e:  # noqa: BLE001 — any failure ends only this feature
            failed.add(step.name)
            _error(step.name, e)


def apply(
    host: str,
    root: Path = ROOT,
    dry_run: bool = False,
    package: str = PACKAGE,
    platform_package: str = platforms.PACKAGE,
    cfg: dict | None = None,
) -> int:
    """Bring this machine in line with HOST's config (CFG, resolved from ROOT
    when not given); 1 when something failed or was not run."""
    cfg = config.resolve(host, root) if cfg is None else cfg
    engine.DRY_RUN = dry_run
    engine.printed = False
    failed: set[str] = set()
    try:
        system = platforms.detect(cfg, platform_package)
        found = steps(cfg, system, package)
        with ExitStack() as sessions:  # left after a failure and on Ctrl-C too
            for step in found:
                sessions.enter_context(step.feature.session(system))
            _phases(host, root, cfg, system, found, failed)
        if not engine.printed and not failed:
            print("nothing to change")
    finally:  # after a failure and on Ctrl-C too
        engine.print_notices()
    return 1 if failed else 0
