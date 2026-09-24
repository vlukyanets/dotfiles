"""dotfiles apply: every feature module and the dotfiles, each after the
steps that provide what it requires, and the notices at the end."""

import graphlib
import importlib
import os
import pkgutil
import sys
from pathlib import Path
from typing import NamedTuple

from dotfiles import config, engine, render
from dotfiles.config import ROOT, ConfigError

PACKAGE = "dotfiles.features"
# The deploy of home/: a step without a module that provides "dotfiles".
DEPLOY = "dotfiles"


class Step(NamedTuple):
    name: str  # the module's name; DEPLOY for the deploy
    gate: str | None  # runs only when features.<gate>.enabled; None: always
    provides: tuple[str, ...]  # capabilities other steps can require
    requires: tuple[str, ...]  # capabilities whose providers run first
    module: object | None
    after: tuple[str, ...] = ()  # the steps providing what it requires


def steps(package: str = PACKAGE) -> list[Step]:
    """Every module of PACKAGE, as a step, after every step that PROVIDES
    what it REQUIRES; the rest by name. A module may declare PROVIDES,
    REQUIRES (capability names, not step names) and, when it is not gated
    by features.<its name>, GATE = "<feature>" or None."""
    found = [Step(DEPLOY, None, (DEPLOY,), (), None)]
    for info in pkgutil.iter_modules(importlib.import_module(package).__path__):
        module = importlib.import_module(f"{package}.{info.name}")
        found.append(
            Step(
                info.name,
                getattr(module, "GATE", info.name),
                tuple(getattr(module, "PROVIDES", ())),
                tuple(getattr(module, "REQUIRES", ())),
                module,
            )
        )
    providers: dict[str, list[str]] = {}
    for step in found:
        for capability in step.provides:
            providers.setdefault(capability, []).append(step.name)
    by_name = {}
    for step in found:
        missing = [c for c in step.requires if c not in providers]
        if missing:
            raise ConfigError(f"{package}.{step.name}: REQUIRES: nothing provides {missing[0]!r}")
        after = {name for c in step.requires for name in providers[c]} - {step.name}
        by_name[step.name] = step._replace(after=tuple(sorted(after)))
    graph = graphlib.TopologicalSorter({name: step.after for name, step in by_name.items()})
    try:
        graph.prepare()
    except graphlib.CycleError as e:
        raise ConfigError(f"{package}: REQUIRES: a cycle: {' → '.join(e.args[1])}") from None
    order = []
    while graph.is_active():
        ready = sorted(graph.get_ready())
        order += ready
        graph.done(*ready)
    return [by_name[name] for name in order]


def _deploy(host: str, root: Path) -> None:
    for line in render.deploy(host, root, dry_run=engine.DRY_RUN):
        print(line)


def apply(
    host: str,
    root: Path = ROOT,
    dry_run: bool = False,
    package: str = PACKAGE,
) -> int:
    """Run HOST's enabled steps; 1 when one failed or was not run for it."""
    cfg = config.resolve(host, root)
    engine.DRY_RUN = dry_run
    if cfg["features"].get("snapper", {}).get("enabled"):
        # What chezmoi's [scriptEnv] gave every script: the pacman hook
        # takes one snapshot pair per apply (features.snapper).
        runtime = os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        os.environ["SNAP_PAC_SKIP"] = "y"
        os.environ["DOTFILES_SNAPPER_STATE"] = f"{runtime}/dotfiles-snapper"
    failed: set[str] = set()
    try:
        for step in steps(package):
            if step.gate and not cfg["features"][step.gate]["enabled"]:
                continue
            blocked = [name for name in step.after if name in failed]
            if blocked:
                failed.add(step.name)
                print(f"error: {step.name}: not run, {', '.join(blocked)} failed", file=sys.stderr)
                continue
            try:
                if step.module is None:
                    _deploy(host, root)
                else:
                    step.module.apply(cfg)
            except engine.Skip:
                pass
            except engine.Deferred as e:
                engine.notice(f"{e} (network?) — the next apply retries")
            except Exception as e:  # noqa: BLE001 — any failure ends only this step
                failed.add(step.name)
                print(f"error: {step.name}: {e}", file=sys.stderr)
    finally:  # after a failure and on Ctrl-C too
        engine.print_notices()
    return 1 if failed else 0
