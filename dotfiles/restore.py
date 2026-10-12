"""dotfiles restore: puts back the files a run of install replaced.

A run's directory in .backups/<node>/ is laid out like a node, its .meta
holding a line for every file, so it is put back the way install puts a
node, and the files it replaces are kept in a new run.
"""

import re
from pathlib import Path

from dotfiles import install
from dotfiles.add import Error
from dotfiles.install import apply, backup_run, make_plan, read_hooks


def restore(repo: Path, node: str, run: str | None = None, paths: list[str] | None = None,
            root: Path = Path("/"), dry_run: bool = False) -> None:
    """Puts each file of .backups/<node>/<run>/ (the last run, when run is
    None), or only those in paths, back under root with its owner and mode.

    Prints each change; with dry_run, prints them and changes nothing.
    """
    runs_dir = repo / ".backups" / node
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node) or not runs_dir.is_dir():
        raise Error(f"no backups of {node}")
    if run is None:
        runs = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
        if not runs:
            raise Error(f"no backups of {node}")
        run = runs[-1]
    run_dir = runs_dir / run
    if not re.fullmatch(r"\d{8}-\d{6}", run) or not run_dir.is_dir():
        raise Error(f"no such backup: {node}/{run}")
    if not root.is_dir():
        raise Error(f"no such directory: {root}")
    keys = None
    if paths:
        keys = {path.lstrip("/") for path in paths}
        for path in paths:
            if not path.startswith("/") or not (run_dir / path.lstrip("/")).is_file():
                raise Error(f"not in backup {node}/{run}: {path}")
    new_run = backup_run(repo, node)
    if new_run == run_dir:
        raise Error(f"backup {node}/{run} was made this second; run restore again")
    try:
        hooks = read_hooks(repo / "nodes" / node / ".hooks")
        apply(make_plan(run_dir, root, {}, new_run, keys, hooks), dry_run)
    finally:
        install.sudo.close()
