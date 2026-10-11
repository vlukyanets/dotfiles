"""dotfiles install: puts nodes/<node>/ onto the machine.

The plan is built first, from the node and the machine, and is written only
when it is complete, so an error found while building it leaves the machine
as it was. An error during the writes can leave a partial install; running
it again completes it. What the user may do is done as the user; the rest
goes to one sudo helper (machine.Sudo).
"""

import functools
import grp
import os
import pwd
import re
import stat
from collections.abc import Callable
from datetime import datetime
from pathlib import Path, PurePosixPath

from dotfiles.add import Error, default_owner, group_name, read_meta, user_name
from dotfiles.machine import Local, Sudo

local = Local()
sudo = Sudo()


def uid_of(name: str) -> int:
    try:
        return pwd.getpwnam(name).pw_uid
    except KeyError:
        raise Error(f"no such user: {name}") from None


def gid_of(name: str) -> int:
    try:
        return grp.getgrnam(name).gr_gid
    except KeyError:
        raise Error(f"no such group: {name}") from None


def now() -> datetime:
    return datetime.now()


def call(op: str, path: str, *args, as_user: bool = True):
    """Does op as the user, or by sudo when as_user is false or the user may not."""
    if as_user:
        try:
            return getattr(local, op)(path, *args)
        except PermissionError:
            pass
        except OSError as e:
            raise Error(f"{op} {path}: {e.strerror}") from e
    return getattr(sudo, op)(path, *args)


def owner_text(uid: int, gid: int) -> str:
    """alice:alice; an id without a name stays a number."""
    names = []
    for name, id in ((user_name, uid), (group_name, gid)):
        try:
            names.append(name(id))
        except KeyError:
            names.append(str(id))
    return ":".join(names)


def replace(path: str, data: bytes, mode: int, uid: int, gid: int, mine: bool,
            backups: Path, run: Path, rel: str, old: bytes, st) -> None:
    """Copies the old file to run/rel as the user's, closed to others, and
    notes its owner and mode in run/.meta; then writes path."""
    backups.mkdir(mode=0o700, exist_ok=True)  # closed: a backup may hold a secret
    (run / rel).parent.mkdir(parents=True, exist_ok=True)
    call("write", str(run / rel), old, 0o600, os.getuid(), os.getgid())
    with open(run / ".meta", "a") as meta:
        meta.write(f"{st[0] & 0o7777:04o} {owner_text(st[1], st[2])} {rel}\n")
    call("write", path, data, mode, uid, gid, as_user=mine)


def install(repo: Path, node: str, root: Path = Path("/"), dry_run: bool = False) -> None:
    """Puts each file of repo/nodes/<node>/ at its path under root, with its
    owner and mode, and fixes the directories that have a .meta line.

    Prints each change; with dry_run, prints them and changes nothing.
    """
    node_dir = repo / "nodes" / node
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node) or not node_dir.is_dir():
        raise Error(f"no such node: {node}")
    if not root.is_dir():
        raise Error(f"no such directory: {root}")
    try:
        plan = make_plan(node_dir, root)
        for line, action in plan:
            print(line)
            if not dry_run:
                action()
    finally:
        sudo.close()


def make_plan(node_dir: Path, root: Path) -> list[tuple[str, Callable[[], None]]]:
    """The lines to print and the actions to do, from reading the node and the machine."""
    files = sorted(
        rel
        for rel in (str(p.relative_to(node_dir)) for p in node_dir.rglob("*") if p.is_file())
        if rel != ".meta"
    )
    meta = {}  # path -> (mode, user, group)
    for key, line in read_meta(node_dir / ".meta").items():
        mode, owner, _ = line.split(" ", 2)
        user, _, group = owner.partition(":")
        if key.startswith("/") or ".." in PurePosixPath(key).parts:
            raise Error(f"{node_dir / '.meta'}: not a path inside the node: {key}")
        if not user or not group:
            raise Error(f"{node_dir / '.meta'}: bad owner: {line}")
        if not (node_dir / key).exists() or key.endswith("/") != (node_dir / key).is_dir():
            raise Error(f"{node_dir / '.meta'}: the node has no {key}")
        meta[key] = (int(mode, 8), user, group)

    def wanted(key: str, default_mode: int) -> tuple[int, int, int]:
        mode, user, group = meta.get(key, (default_mode, *default_owner(key).split(":")))
        return mode, uid_of(user), gid_of(group)

    me = (os.getuid(), os.getgid())
    stamp = now().strftime("%Y%m%d-%H%M%S")  # the start, so one run has one directory
    backups = node_dir.parents[1] / ".backups"
    plan = []

    meta_dirs = [key for key in meta if key.endswith("/")]
    dirs = {f"{parent}/" for rel in files + meta_dirs
            for parent in PurePosixPath(rel).parents if str(parent) != "."}
    for key in sorted(dirs | set(meta_dirs)):
        path = str(root / key)
        mode, uid, gid = wanted(key, 0o755)
        st = call("stat", path)
        if st is None:
            plan.append((f"created {path}/", functools.partial(
                call, "mkdir", path, mode, uid, gid, as_user=(uid, gid) == me)))
        elif not stat.S_ISDIR(st[0]):
            raise Error(f"{not_a(st, 'a directory')}: {path}")
        elif key in meta:
            plan += changes(f"{path}/", path, st, mode, uid, gid)

    for rel in files:
        path = str(root / rel)
        data = (node_dir / rel).read_bytes()
        git_mode = 0o755 if (node_dir / rel).stat().st_mode & 0o100 else 0o644
        mode, uid, gid = wanted(rel, git_mode)
        mine = (uid, gid) == me
        st = call("stat", path)
        if st is None:
            plan.append((f"installed {path}", functools.partial(
                call, "write", path, data, mode, uid, gid, as_user=mine)))
        elif not stat.S_ISREG(st[0]):
            raise Error(f"{not_a(st, 'a regular file')}: {path}")
        elif (old := call("read", path)) != data:
            run = backups / node_dir.name / stamp
            plan.append((f"updated {path} (backup {run / rel})", functools.partial(
                replace, path, data, mode, uid, gid, mine, backups, run, rel, old, st)))
        else:
            plan += changes(path, path, st, mode, uid, gid)
    return plan


def not_a(st: tuple[int, int, int], what: str) -> str:
    return "symlinks are not supported" if stat.S_ISLNK(st[0]) else f"not {what}"


def changes(label: str, path: str, st, mode: int, uid: int, gid: int):
    """The chown and chmod that bring path, stat st, to the wanted owner and mode."""
    plan = []
    current = st[0] & 0o7777
    if (st[1], st[2]) != (uid, gid):
        if stat.S_ISREG(st[0]):
            # A chown clears a file's setuid, and its setgid if the group may run it.
            current &= ~(0o4000 | (0o2000 if current & 0o010 else 0))
        plan.append((f"owner {label} {owner_text(st[1], st[2])} → {owner_text(uid, gid)}",
                     functools.partial(call, "chown", path, uid, gid)))
    if current != mode:
        plan.append((f"mode {label} {current:04o} → {mode:04o}",
                     functools.partial(call, "chmod", path, mode)))
    return plan
