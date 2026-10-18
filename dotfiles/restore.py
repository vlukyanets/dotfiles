"""dotfiles restore: puts back the files a run of install replaced.

A run's directory in .backups/<host>/ is laid out like a host, its .meta
holding a line for every file, so it is put back the way install puts a
host, and the files it replaces are kept in a new run.
"""

import re
from pathlib import Path

from dotfiles import install
from dotfiles.add import HOST_NAME, Error
from dotfiles.install import apply, backup_run, make_plan, read_hooks


def restore(repo: Path, host: str, run: str | None = None, paths: list[str] | None = None,
            root: Path = Path("/"), dry_run: bool = False) -> None:
    """Puts each file of .backups/<host>/<run>/ (the last run, when run is
    None), or only those in paths, back under root with its owner and mode.

    Prints each change; with dry_run, prints them and changes nothing.
    """
    runs_dir = repo / ".backups" / host
    if not HOST_NAME.fullmatch(host) or not runs_dir.is_dir():
        raise Error(f"no backups of {host}")
    if run is None:
        runs = sorted(p.name for p in runs_dir.iterdir() if p.is_dir())
        if not runs:
            raise Error(f"no backups of {host}")
        run = runs[-1]
    run_dir = runs_dir / run
    if not re.fullmatch(r"\d{8}-\d{6}", run) or not run_dir.is_dir():
        raise Error(f"no such backup: {host}/{run}")
    if not root.is_dir():
        raise Error(f"no such directory: {root}")
    keys = None
    if paths:
        keys = {path.lstrip("/") for path in paths}
        for path in paths:
            held = run_dir / path.lstrip("/")
            if not path.startswith("/") or not (held.is_file() or held.is_symlink()):
                raise Error(f"not in backup {host}/{run}: {path}")
    new_run = backup_run(repo, host)
    if new_run == run_dir:
        raise Error(f"backup {host}/{run} was made this second; run restore again")
    try:
        hooks = read_hooks(repo / "hosts" / host / ".hooks")
        apply(make_plan(run_dir, root, {}, new_run, keys, hooks), dry_run)
    finally:
        install.sudo.close()
