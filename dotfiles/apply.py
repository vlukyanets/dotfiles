"""dotfiles apply: every feature module and the dotfiles, each after the
steps it needs, and the notices at the end."""

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
# The deploy of home/: a step without a module, which features can need.
DEPLOY = "dotfiles"


class Step(NamedTuple):
    name: str  # the module's name; DEPLOY for the deploy
    gate: str | None  # runs only when features.<gate>.enabled; None: always
    needs: tuple[str, ...]  # steps that run first and must not have failed
    module: object | None


def steps(package: str = PACKAGE) -> list[Step]:
    """Every module of PACKAGE, as a step, after the steps it NEEDS; the
    rest by name. A module declares NEEDS = (...) and, when it is not
    gated by features.<its name>, GATE = "<feature>" or None."""
    found = {DEPLOY: Step(DEPLOY, None, (), None)}
    for info in pkgutil.iter_modules(importlib.import_module(package).__path__):
        module = importlib.import_module(f"{package}.{info.name}")
        gate = getattr(module, "GATE", info.name)
        found[info.name] = Step(info.name, gate, tuple(getattr(module, "NEEDS", ())), module)
    for step in found.values():
        for need in step.needs:
            if need not in found:
                raise ConfigError(f"{package}.{step.name}: NEEDS: no step {need!r}")
    graph = graphlib.TopologicalSorter({name: step.needs for name, step in found.items()})
    try:
        graph.prepare()
    except graphlib.CycleError as e:
        raise ConfigError(f"{package}: NEEDS: a cycle: {' → '.join(e.args[1])}") from None
    order = []
    while graph.is_active():
        ready = sorted(graph.get_ready())
        order += ready
        graph.done(*ready)
    return [found[name] for name in order]


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
            blocked = [name for name in step.needs if name in failed]
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
