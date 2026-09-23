"""dotfiles apply: the features in order, the dotfiles, then the steps that
need the dotfiles, and the notices at the end."""

import importlib
import os
import sys
from pathlib import Path
from typing import NamedTuple

from dotfiles import config, engine, render
from dotfiles.config import ROOT


class Step(NamedTuple):
    module: str  # dotfiles/features/<module>.py; "dotfiles" is the deploy
    gate: str | None  # runs only when features.<gate>.enabled
    needs: tuple[str, ...] = ()  # earlier steps that must not have failed


STEPS = [
    Step("nobeep", "nobeep"),
    Step("dotfiles", None),
]


def _deploy(host: str, root: Path) -> None:
    for line in render.deploy(host, root, dry_run=engine.DRY_RUN):
        print(line)


def apply(
    host: str,
    root: Path = ROOT,
    dry_run: bool = False,
    steps: list[Step] = STEPS,
    package: str = "dotfiles.features",
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
        for step in steps:
            if step.gate and not cfg["features"][step.gate]["enabled"]:
                continue  # never imported: a disabled feature has no side effects
            blocked = [name for name in step.needs if name in failed]
            if blocked:
                failed.add(step.module)
                print(
                    f"error: {step.module}: not run, {', '.join(blocked)} failed", file=sys.stderr
                )
                continue
            try:
                if step.module == "dotfiles":
                    _deploy(host, root)
                else:
                    importlib.import_module(f"{package}.{step.module}").apply(cfg)
            except engine.Skip:
                pass
            except engine.Deferred as e:
                engine.notice(f"{e} (network?) — the next apply retries")
            except Exception as e:  # noqa: BLE001 — any failure ends only this step
                failed.add(step.module)
                print(f"error: {step.module}: {e}", file=sys.stderr)
    finally:  # after a failure and on Ctrl-C too
        engine.print_notices()
    return 1 if failed else 0
