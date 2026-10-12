"""The packages of a node: nodes/<node>/.packages, one name per line.

A node is one machine, so the names are those of its distribution, which
/etc/os-release names. Packages the machine has and the list lacks are
not this command's business: it only installs what is missing.
"""

import functools
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

from dotfiles.machine import Error

FILE = ".packages"


def read(node_dir: Path) -> list[str]:
    path = node_dir / FILE
    return [line.strip() for line in path.read_text().splitlines() if line.strip()] if path.exists() else []


def write(node_dir: Path, names: list[str]) -> None:
    """Writes names sorted, or removes the file when there are none."""
    path = node_dir / FILE
    if names:
        node_dir.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(name + "\n" for name in sorted(set(names))))
    else:
        path.unlink(missing_ok=True)


def family() -> str:
    """arch or debian: the distribution of this machine, or the one it is like."""
    fields = {}
    for name in ("/etc/os-release", "/usr/lib/os-release"):
        if Path(name).exists():
            for line in Path(name).read_text().splitlines():
                key, _, value = line.partition("=")
                fields[key] = value.strip("\"'")
            break
    ids = [fields.get("ID", "")] + fields.get("ID_LIKE", "").split()
    for known in ("arch", "debian"):
        if known in ids:
            return known
    raise Error(f"only Arch, Debian and the distributions like them are supported, "
                f"not {fields.get('ID') or 'one without /etc/os-release'}")


def run(command: list[str], capture: bool = False) -> str:
    """Runs command, as the user; its output when capture is set."""
    try:
        done = subprocess.run(command, capture_output=capture, text=True, check=False)
    except FileNotFoundError:
        raise Error(f"{command[0]} is needed for packages") from None
    if done.returncode:
        raise Error(f"{' '.join(command)}: exited with {done.returncode}")
    return done.stdout if capture else ""


def installed() -> set[str]:
    """The names of the packages installed on this machine."""
    if family() == "arch":
        return set(run(["pacman", "-Qq"], capture=True).split())
    lines = run(["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Package}\n"], capture=True)
    return {line.split()[-1] for line in lines.splitlines() if line.startswith("ii ")}


def install_command(names: list[str]) -> list[str]:
    if family() == "debian":
        return ["sudo", "apt-get", "install", *names]
    if shutil.which("paru"):  # paru asks sudo itself, and builds from the AUR as the user
        return ["paru", "-S", "--needed", *names]
    return ["sudo", "pacman", "-S", "--needed", *names]


def install(names: list[str]) -> None:
    run(install_command(names))


def missing(node_dir: Path) -> list[str]:
    """The packages of the node this machine lacks."""
    names = read(node_dir)
    if not names:
        return []
    have = installed()
    return [name for name in names if name not in have]


def plan(node_dir: Path, root: Path) -> list[tuple[str, Callable[[], None]]]:
    """The line to print and the action to install what the machine lacks."""
    if not read(node_dir):
        return []
    if str(root) != "/":  # Another root is not this machine's running system.
        return [(f"skipped packages (the root is {root})", lambda: None)]
    names = missing(node_dir)
    if not names:
        return []
    return [(f"installed packages {' '.join(names)}",
             functools.partial(install, names))]
