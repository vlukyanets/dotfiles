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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from dotfiles import template
from dotfiles.add import Error, default_owner, group_name, read_meta, user_name
from dotfiles.machine import Local, Stat, Sudo

local = Local()
sudo = Sudo()
STAMP = "%Y%m%d-%H%M%S"  # the name of a run in .backups/<node>/


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
            backups: Path, run: Path, rel: str, old: bytes, st: Stat) -> None:
    """Copies the old file to run/rel as the user's, closed to others, and
    notes its owner and mode in run/.meta; then writes path."""
    backups.mkdir(mode=0o700, exist_ok=True)  # closed: a backup may hold a secret
    (run / rel).parent.mkdir(parents=True, exist_ok=True)
    call("write", str(run / rel), old, 0o600, os.getuid(), os.getgid())
    with open(run / ".meta", "a") as meta:
        meta.write(f"{st.mode & 0o7777:04o} {owner_text(st.uid, st.gid)} {rel}\n")
    call("write", path, data, mode, uid, gid, as_user=mine)


def node_dir_of(repo: Path, node: str, root: Path) -> Path:
    """repo/nodes/<node>/, once it and root are checked."""
    node_dir = repo / "nodes" / node
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node) or not node_dir.is_dir():
        raise Error(f"no such node: {node}")
    if not root.is_dir():
        raise Error(f"no such directory: {root}")
    return node_dir


def install(repo: Path, node: str, root: Path = Path("/"), dry_run: bool = False) -> None:
    """Puts each file of repo/nodes/<node>/ at its path under root, with its
    owner and mode, and fixes the directories that have a .meta line.

    Prints each change; with dry_run, prints them and changes nothing.
    """
    node_dir = node_dir_of(repo, node, root)
    try:
        values = template.values_for(node_dir, ask=not dry_run)
        apply(make_plan(node_dir, root, values, backup_run(repo, node)), dry_run)
    finally:
        sudo.close()


def backup_run(repo: Path, node: str) -> Path:
    """Where a run keeps the files it replaces, named by its start, so one
    run has one directory."""
    return repo / ".backups" / node / now().strftime(STAMP)


def apply(plan: list[tuple[str, Callable[[], None]]], dry_run: bool) -> None:
    """Prints each line of plan and, unless dry_run, does its action."""
    for line, action in plan:
        print(line)
        if not dry_run:
            action()


@dataclass
class Item:
    """A path of the node: what the node wants there, and what the machine has."""
    key: str  # its path in the node; a directory's ends in a slash
    path: str  # its path on the machine
    mode: int
    uid: int
    gid: int
    in_meta: bool
    st: Stat | None  # None when the machine does not have it
    data: bytes = b""  # a file's contents in the node, a template's filled
    machine_data: bytes = b""  # and on the machine
    missing: tuple[str, ...] = ()  # the values a template lacks; data is empty then


def survey(node_dir: Path, root: Path, values: dict[str, str]) -> list[Item]:
    """Every directory of the node, parents first, then every file, read
    from the node and the machine; a template is filled with values."""
    files = sorted(
        rel
        for rel in (str(p.relative_to(node_dir)) for p in node_dir.rglob("*") if p.is_file())
        if rel != ".meta"
    )
    meta: dict[str, tuple[int, str, str]] = {}  # path -> (mode, user, group)
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
        if key in meta:
            mode, user, group = meta[key]
        else:
            mode, (user, group) = default_mode, default_owner(key).split(":")
        return mode, uid_of(user), gid_of(group)

    items = []
    meta_dirs = [key for key in meta if key.endswith("/")]
    dirs = {f"{parent}/" for rel in files + meta_dirs
            for parent in PurePosixPath(rel).parents if str(parent) != "."}
    for key in sorted(dirs | set(meta_dirs)):
        path = str(root / key)
        st = call("stat", path)
        if st is not None and not stat.S_ISDIR(st.mode):
            raise Error(f"{not_a(st, 'a directory')}: {path}")
        items.append(Item(key, path, *wanted(key, 0o755), key in meta, st))

    for rel in files:
        target = rel.removesuffix(template.SUFFIX)
        if target != rel and target in files:
            raise Error(f"{node_dir}: both {target} and its template {rel}")
        data, missing = (node_dir / rel).read_bytes(), tuple[str, ...]()
        if target != rel:
            text = template.text_of(node_dir / rel)
            missing = tuple(name for name in template.names(text) if name not in values)
            data = b"" if missing else template.fill(text, values).encode()
        path = str(root / target)
        git_mode = 0o755 if (node_dir / rel).stat().st_mode & 0o100 else 0o644
        st = call("stat", path)
        if st is not None and not stat.S_ISREG(st.mode):
            raise Error(f"{not_a(st, 'a regular file')}: {path}")
        items.append(Item(rel, path, *wanted(rel, git_mode), rel in meta, st,
                          data, call("read", path) if st else b"", missing))
    return items


def make_plan(node_dir: Path, root: Path, values: dict[str, str], run: Path,
              keys: set[str] | None = None) -> list[tuple[str, Callable[[], None]]]:
    """The lines to print and the actions to do, from reading the node and
    the machine; a file replaced is kept in run. With keys, only those files
    of the node, and the directories above them."""
    me = (os.getuid(), os.getgid())
    backups = run.parents[1]
    plan: list[tuple[str, Callable[[], None]]] = []
    items = survey(node_dir, root, values)
    if keys is not None:
        items = [item for item in items if item.key in keys
                 or item.key.endswith("/") and any(key.startswith(item.key) for key in keys)]
    for item in items:
        path, mode, uid, gid = item.path, item.mode, item.uid, item.gid
        mine = (uid, gid) == me
        if item.key.endswith("/"):
            if item.st is None:
                plan.append((f"created {path}/", functools.partial(
                    call, "mkdir", path, mode, uid, gid, as_user=mine)))
            elif item.in_meta:
                plan += changes(f"{path}/", item)
        elif item.missing:  # Only in a dry run: a real one has asked for them.
            plan.append((f"unfilled {path} ({', '.join(item.missing)})", lambda: None))
        elif item.st is None:
            plan.append((f"installed {path}", functools.partial(
                call, "write", path, item.data, mode, uid, gid, as_user=mine)))
        elif item.machine_data != item.data:
            rel = item.key.removesuffix(template.SUFFIX)  # the machine's file, not the template
            plan.append((f"updated {path} (backup {run / rel})", functools.partial(
                replace, path, item.data, mode, uid, gid, mine, backups, run, rel,
                item.machine_data, item.st)))
        else:
            plan += changes(path, item)
    return plan


def not_a(st: Stat, what: str) -> str:
    return "symlinks are not supported" if stat.S_ISLNK(st.mode) else f"not {what}"


def changes(label: str, item: Item):
    """The chown and chmod that bring item's path to its wanted owner and mode."""
    plan: list[tuple[str, Callable[[], None]]] = []
    st, path = item.st, item.path
    assert st is not None  # Only a path the machine has is changed.
    current = st.mode & 0o7777
    if (st.uid, st.gid) != (item.uid, item.gid):
        if stat.S_ISREG(st.mode):
            # A chown clears a file's setuid, and its setgid if the group may run it.
            current &= ~(0o4000 | (0o2000 if current & 0o010 else 0))
        plan.append((f"owner {label} {owner_text(st.uid, st.gid)} → {owner_text(item.uid, item.gid)}",
                     functools.partial(call, "chown", path, item.uid, item.gid)))
    if current != item.mode:
        plan.append((f"mode {label} {current:04o} → {item.mode:04o}",
                     functools.partial(call, "chmod", path, item.mode)))
    return plan
