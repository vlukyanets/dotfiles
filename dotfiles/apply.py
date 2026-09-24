"""dotfiles apply: the platform, the packages of every feature at once, the
dotfiles, then the features in the order their packages need each other,
and the notices at the end."""

import importlib
import os
import pkgutil
import sys
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


def steps(cfg: dict, system: Platform, package: str = PACKAGE) -> list[Step]:
    """The features of PACKAGE that are enabled and have a strategy for
    SYSTEM, by name. A module whose name is not a feature in the schema is
    not switched by one: it always runs and reads its flags itself."""
    found = []
    for info in sorted(pkgutil.iter_modules(importlib.import_module(package).__path__)):
        name = info.name
        if name in cfg["features"] and not cfg["features"][name]["enabled"]:
            continue
        module = importlib.import_module(f"{package}.{name}")
        classes = [c for c in platforms.classes(module) if issubclass(c, Feature)]
        if len(classes) != 1:
            raise ConfigError(f"{package}.{name}: defines {len(classes)} features, not one")
        feature = classes[0](cfg)
        strategy = feature.strategy(system)
        if strategy is not None:  # none: the feature does not apply here
            packages, replaces = frozenset(strategy.packages()), frozenset(strategy.replaces())
            found.append(Step(name, feature, strategy, packages, replaces))
    return found


def order(steps: list[Step], depends: dict[str, set[str]]) -> list[tuple[Step, list[str]]]:
    """STEPS in running order, each with the names of the steps it runs
    after: B after A when a package of B needs a package that A has and B
    does not. Ties go by name; a cycle in the package graph is broken by
    name too."""
    owners: dict[str, set[str]] = {}
    for step in steps:
        for pkg in step.packages:
            owners.setdefault(pkg, set()).add(step.name)
    after = {
        step.name: sorted(
            {
                owner
                for pkg in step.packages
                for dep in depends.get(pkg, ())
                if dep not in step.packages
                for owner in owners.get(dep, ())
            }
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


def _deploy(host: str, root: Path) -> None:
    for line in render.deploy(host, root, dry_run=engine.DRY_RUN):
        print(line)


def _error(name: str, msg) -> None:
    print(f"error: {name}: {msg}", file=sys.stderr)


def apply(
    host: str,
    root: Path = ROOT,
    dry_run: bool = False,
    package: str = PACKAGE,
    platform_package: str = platforms.PACKAGE,
) -> int:
    """Bring this machine in line with HOST's config; 1 when something failed
    or was not run."""
    cfg = config.resolve(host, root)
    engine.DRY_RUN = dry_run
    if cfg["features"].get("snapper", {}).get("enabled"):
        # For every command of this apply: the pacman hook takes one
        # snapshot pair per apply, not one per transaction (features.snapper).
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        os.environ["SNAP_PAC_SKIP"] = "y"
        os.environ["DOTFILES_SNAPPER_STATE"] = f"{runtime}/dotfiles-snapper"
    failed: set[str] = set()
    try:
        system = platforms.detect(cfg, platform_package)
        found = steps(cfg, system, package)
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
            _deploy(host, root)
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
    finally:  # after a failure and on Ctrl-C too
        engine.print_notices()
    return 1 if failed else 0
