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
import subprocess
import sys
from pathlib import Path, PurePosixPath


class Error(Exception):
    """A problem with the input or the machine, reported to the user."""


# What a secret looks like, most specific first; a line reports the first
# rule it matches. NOTE: these catch known token formats and obvious
# assignments only, so a file they pass may still hold a secret.
SECRET_RULES = {
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_\w{82}\b"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"),
    "API key": re.compile(r"\bsk-(?:ant-|proj-)?[A-Za-z0-9_-]{32,}"),
    "password or key": re.compile(
        r"(?i)^[ \t]*(?:\w*[_-])?(?:password|passwd|passphrase|psk|secret|token|api_?key)"
        r"[ \t]*[:=][ \t]*\S"
    ),
}


def find_secrets(data: bytes) -> list[tuple[int, str]]:
    """The line numbers and rule names of what looks like a secret."""
    found = []
    for number, line in enumerate(data.decode(errors="replace").splitlines(), 1):
        for name, rule in SECRET_RULES.items():
            if rule.search(line):
                found.append((number, name))
                break
    return found


def user_name(uid: int) -> str:
    return pwd.getpwuid(uid).pw_name


def group_name(gid: int) -> str:
    return grp.getgrgid(gid).gr_name


def sudo(*args: str) -> bytes:
    try:
        return subprocess.run(["sudo", *args], check=True, capture_output=True).stdout
    except subprocess.CalledProcessError as e:
        raise Error(f"sudo {' '.join(args)}: {e.stderr.decode().strip()}") from e


def sudo_read(path: Path) -> bytes:
    return sudo("cat", "--", str(path))


def sudo_stat(path: Path, follow: bool) -> tuple[int, int, int]:
    fields = sudo("stat", *(["-L"] if follow else []), "-c", "%f %u %g", "--", str(path)).split()
    return int(fields[0], 16), int(fields[1]), int(fields[2])


def mode_and_ids(path: Path, follow: bool = False) -> tuple[int, int, int]:
    """The st_mode, uid and gid of path, through sudo when a directory on the
    way is closed to the user. Without follow, a symlink is not followed."""
    try:
        st = path.stat(follow_symlinks=follow)
    except FileNotFoundError:
        raise Error(f"no such file: {path}") from None
    except PermissionError:
        return sudo_stat(path, follow)
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
    """
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

    contents = {}
    secrets = []
    for path in paths:
        src = root / path.lstrip("/")
        if not mode_and_ids(src)[0] & 0o004:
            print(f"warning: {path} is closed to others; it may hold a secret, "
                  "check it before committing", file=sys.stderr)
        try:
            contents[path] = src.read_bytes()
        except PermissionError:
            contents[path] = sudo_read(src)
        secrets += [f"{path}:{number}: {name}" for number, name in find_secrets(contents[path])]
    if secrets and not force:
        raise Error("these look like secrets; keep the file as a template, "
                    "or pass --force to copy it anyway:\n  " + "\n  ".join(secrets))
    for secret in secrets:
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
