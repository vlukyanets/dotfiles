"""dotfiles cleanup: removes the backups dotfiles install keeps in .backups/.

A run's backups are one directory, .backups/<node>/<YYYYmmdd-HHMMSS>/,
named by the time the run started.
"""

import shutil
from datetime import datetime, timedelta
from pathlib import Path

from dotfiles.add import Error
from dotfiles.install import STAMP


def now() -> datetime:
    return datetime.now()


def cleanup(repo: Path, keep: int | None = None, older_than: int | None = None,
            dry_run: bool = False) -> None:
    """Removes every run, or all but the last keep runs of each node, or the
    runs older than older_than days.

    Prints each run it removes; with dry_run, prints them and removes none.
    """
    if (keep or 0) < 0 or (older_than or 0) < 0:
        raise Error("the number must not be negative")
    backups = repo / ".backups"
    nodes = sorted(backups.iterdir()) if backups.is_dir() else []
    doomed = []
    for node in nodes:
        runs = sorted(node.iterdir())
        for run in runs:
            try:
                datetime.strptime(run.name, STAMP)
            except ValueError:
                raise Error(f"not a backup: {run}") from None
        if keep is not None:
            runs = runs[:max(len(runs) - keep, 0)]
        elif older_than is not None:
            cutoff = now() - timedelta(days=older_than)
            runs = [run for run in runs if datetime.strptime(run.name, STAMP) < cutoff]
        doomed += runs
    for run in doomed:
        print(f"removed {run}")
        if not dry_run:
            shutil.rmtree(run)
