"""dotfiles add: copies machine files into nodes/<node>/ and keeps .meta.

nodes/<node>/.meta lists, one per line as `<mode> <owner>:<group> <path>`,
the files and the directories above them whose owner or mode differ from
the defaults: <user>:<user> for home/<user>/ and below, root:root elsewhere;
0644 for a file, or 0755 if executable; 0755 for a directory. A directory's
path ends in a slash: `0700 alice:alice home/alice/`.
"""

import grp
import pwd
import re
import stat
import sys
from pathlib import Path, PurePosixPath

from dotfiles import secrets
from dotfiles.machine import Error, Sudo
from dotfiles.template import SUFFIX

sudo = Sudo()


def user_name(uid: int) -> str:
    return pwd.getpwuid(uid).pw_name


def group_name(gid: int) -> str:
    return grp.getgrgid(gid).gr_name


def mode_and_ids(path: Path, follow: bool = False) -> tuple[int, int, int]:
    """The st_mode, uid and gid of path, through sudo when a directory on the
    way is closed to the user. Without follow, a symlink is not followed."""
    try:
        st = path.stat(follow_symlinks=follow)
    except FileNotFoundError:
        raise Error(f"no such file: {path}") from None
    except PermissionError:
        found = sudo.stat(str(path), follow)
        if found is None:
            raise Error(f"no such file: {path}") from None
        return found
    return st.st_mode, st.st_uid, st.st_gid


def default_owner(key: str) -> str:
    """The default owner of a .meta key: a file path, or a directory path
    ending in a slash."""
    parts = key.split("/")
    if parts[0] == "home" and len(parts) >= 3:
        return f"{parts[1]}:{parts[1]}"
    return "root:root"


def read_meta(path: Path) -> dict[str, str]:
    """The lines of a .meta file by their path."""
    if not path.exists():
        return {}
    lines = {}
    for number, line in enumerate(path.read_text().splitlines(), 1):
        fields = line.split(" ", 2)
        if len(fields) != 3 or not re.fullmatch(r"[0-7]{4}", fields[0]):
            raise Error(f"{path}:{number}: not `<mode> <owner>:<group> <path>`")
        lines[fields[2]] = line
    return lines


def add(
    repo: Path,
    node: str,
    paths: list[str],
    root: Path = Path("/"),
    dry_run: bool = False,
    force: bool = False,
) -> None:
    """Copies each path from root into repo/nodes/<node>/ and updates .meta.

    Prints each change; with dry_run, prints them and changes nothing.
    Refuses files that look like they hold a secret, unless force is set.
    What the user cannot read goes to one sudo helper (machine.Sudo).
    """
    try:
        copy(repo, node, paths, root, dry_run, force)
    finally:
        sudo.close()


def copy(repo: Path, node: str, paths: list[str], root: Path, dry_run: bool, force: bool) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node):
        raise Error(f"bad node name: {node}")
    for path in paths:
        if not path.startswith("/"):
            raise Error(f"not an absolute path: {path}")
        st_mode = mode_and_ids(root / path.lstrip("/"))[0]
        if stat.S_ISLNK(st_mode):
            raise Error(f"symlinks are not supported: {path}")
        if not stat.S_ISREG(st_mode):
            raise Error(f"not a regular file: {path}")
        if path.endswith(SUFFIX):
            raise Error(f"a node reads a file ending in {SUFFIX} as a template: {path}")
        kept = f"nodes/{node}/{path.lstrip('/')}{SUFFIX}"
        if (repo / kept).exists():
            raise Error(f"{path} is kept as a template, {kept}; change that instead")

    config = secrets.load(repo / "secret_leaks.toml")
    contents = {}
    found = []
    for path in paths:
        src = root / path.lstrip("/")
        if not mode_and_ids(src)[0] & 0o004:
            print(f"warning: {path} is closed to others; it may hold a secret, "
                  "check it before committing", file=sys.stderr)
        try:
            contents[path] = src.read_bytes()
        except PermissionError:
            contents[path] = sudo.read(str(src))
        found += secrets.report(path, secrets.find_secrets(config, contents[path], path))
    if found and not force:
        raise Error("these look like secrets; keep the file as a template, "
                    "or pass --force to copy it anyway:\n  " + "\n  ".join(found))
    for secret in found:
        print(f"warning: copying a secret: {secret}", file=sys.stderr)

    node_dir = repo / "nodes" / node
    meta_path = node_dir / ".meta"
    meta = read_meta(meta_path)
    old_meta = dict(meta)

    for path in paths:
        rel = path.lstrip("/")
        src = root / rel
        mode = mode_and_ids(src)[0] & 0o7777
        data = contents[path]
        git_mode = 0o755 if mode & 0o100 else 0o644

        dest = node_dir / rel
        if not dest.exists():
            change = "added"
        elif dest.read_bytes() != data or dest.stat().st_mode & 0o777 != git_mode:
            change = "updated"
        else:
            change = "unchanged"
        print(f"{change} nodes/{node}/{rel}")
        if change != "unchanged" and not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            dest.chmod(git_mode)

        update_meta(meta, rel, mode_and_ids(src), git_mode)
        for parent in PurePosixPath(rel).parents[:-1]:
            update_meta(meta, f"{parent}/", mode_and_ids(root / parent, follow=True), 0o755)

    if meta != old_meta and not dry_run:
        if meta:
            node_dir.mkdir(parents=True, exist_ok=True)
            meta_path.write_text("".join(meta[key] + "\n" for key in sorted(meta)))
        else:
            meta_path.unlink()


def update_meta(
    meta: dict[str, str], key: str, ids: tuple[int, int, int], default_mode: int
) -> None:
    """Sets, keeps or removes the line for key, printing a change."""
    st_mode, uid, gid = ids
    mode = st_mode & 0o7777
    owner = f"{user_name(uid)}:{group_name(gid)}"
    if mode == default_mode and owner == default_owner(key):
        if meta.pop(key, None) is not None:
            print(f"meta: removed {key}")
        return
    line = f"{mode:04o} {owner} {key}"
    if meta.get(key) != line:
        meta[key] = line
        print(f"meta: set {line}")
