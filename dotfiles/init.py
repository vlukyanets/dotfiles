"""dotfiles init: clones the repository the command works on, as chezmoi does.

The command finds its repository in the checkout its own code runs from
(`uv run` in a clone), else in $DOTFILES_REPO, else in
~/.local/share/dotfiles (under $XDG_DATA_HOME when it is set), where init
clones it for a command installed with `uv tool install`.
"""

import os
import subprocess
from pathlib import Path

from dotfiles.machine import Error

URL = "https://github.com/vlukyanets/dotfiles"
MARK = "secret_leaks.toml"  # a file every clone has and an installed package does not


def clone_dir() -> Path:
    """Where init clones the repository: $DOTFILES_REPO, or the default."""
    if repo := os.environ.get("DOTFILES_REPO"):
        return Path(repo)
    data = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share"
    return Path(data) / "dotfiles"


def find_repo() -> Path:
    here = Path(__file__).resolve().parents[1]
    repo = here if (here / MARK).is_file() else clone_dir()
    if not (repo / MARK).is_file():
        raise Error(f"no dotfiles repository in {repo}; run dotfiles init")
    return repo


def init(url: str = URL, dry_run: bool = False, slim: bool = False) -> None:
    """Clones url into clone_dir(), which must be missing or empty; with
    slim, without the old versions of files, which git fetches when asked.

    Prints what it does; with dry_run, prints it and does nothing.
    """
    target = clone_dir()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise Error(f"already there, and not empty: {target}")
    print(f"cloned {url} into {target}{' (slim)' if slim else ''}")
    if dry_run:
        return
    try:
        subprocess.run(["git", "clone", "--quiet", *(["--filter=blob:none"] if slim else []),
                        url, str(target)],
                       check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise Error("git is needed to clone the repository") from None
    except subprocess.CalledProcessError as e:
        raise Error(f"git clone {url}: {e.stderr.strip()}") from None
