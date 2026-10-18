"""dotfiles add: copies machine files into hosts/<host>/ and keeps .meta.

hosts/<host>/.meta lists, one per line as `<mode> <owner>:<group> <path>`,
the files and the directories above them whose owner or mode differ from
the defaults: <user>:<user> for home/<user>/ and below, root:root elsewhere;
0644 for a file, or 0755 if executable; 0755 for a directory. A directory's
path ends in a slash: `0700 alice:alice home/alice/`.
"""

import grp
import os
import pwd
import re
import stat
import sys
from pathlib import Path, PurePosixPath

from dotfiles import packages as host_packages
from dotfiles import secrets, template
from dotfiles.machine import Error, Stat, Sudo
from dotfiles.template import SUFFIX

sudo = Sudo()
HOST_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9-]*(\.[A-Za-z0-9-]+)*")  # a hostname, matched whole
OWN = (".meta", ".hooks", ".packages")  # the files of a host that are its own, not the machine's


def user_name(uid: int) -> str:
    return pwd.getpwuid(uid).pw_name


def group_name(gid: int) -> str:
    return grp.getgrgid(gid).gr_name


def mode_and_ids(path: Path, follow: bool = False) -> Stat:
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
    return Stat(st.st_mode, st.st_uid, st.st_gid)


def default_owner(key: str) -> str:
    """The default owner of a .meta key: a file path, or a directory path
    ending in a slash."""
    parts = key.split("/")
    if parts[0] == "home" and len(parts) >= 3:
        return f"{parts[1]}:{parts[1]}"
    return "root:root"


def symlink_on_the_way(host_dir: Path, rel: str) -> str | None:
    """The first directory above rel in the host that is a symlink, so that
    nothing is read, written or removed through it."""
    return next((str(parent) for parent in reversed(PurePosixPath(rel).parents[:-1])
                 if (host_dir / parent).is_symlink()), None)


def parse_meta(path: Path) -> tuple[dict[str, str], list[str]]:
    """The good lines of a .meta file by their path, and a problem for each bad one."""
    try:
        text = path.read_bytes().decode() if path.exists() else ""
    except UnicodeDecodeError:
        return {}, [f"{path}: not UTF-8 text"]
    lines: dict[str, str] = {}
    problems = []
    for number, line in enumerate(text.splitlines(), 1):
        fields = line.split(" ", 2)
        if len(fields) != 3 or not re.fullmatch(r"[0-7]{4}", fields[0]):
            problems.append(f"{path}:{number}: not `<mode> <owner>:<group> <path>`")
        else:
            lines[fields[2]] = line
    return lines, problems


def read_meta(path: Path) -> dict[str, str]:
    """The lines of a .meta file by their path; an error lists every bad one."""
    lines, problems = parse_meta(path)
    if problems:
        raise Error("\n  ".join(problems))
    return lines


def add(
    repo: Path,
    host: str,
    paths: list[str],
    root: Path = Path("/"),
    dry_run: bool = False,
    force: bool = False,
    as_template: bool = False,
    packages: list[str] | None = None,
) -> None:
    """Copies each path from root into repo/hosts/<host>/ and updates .meta,
    then adds each of packages, which must be installed, to its .packages.
    With neither, copies each file and symlink of the host that changed on
    the machine, and names the changes it cannot copy (status.drifted).

    Prints each change; with dry_run, prints them and changes nothing.
    Refuses files that look like they hold a secret, unless force is set.
    With as_template, keeps each as a template instead, its secrets named
    and moved to the host's values file (template.py).
    What the user cannot read goes to one sudo helper (machine.Sudo).
    """
    if not HOST_NAME.fullmatch(host):
        raise Error(f"bad host name: {host}")
    if not paths and not packages:  # Everything that changed on the machine, as status shows it.
        if as_template:
            raise Error("--template needs the paths to make templates of")
        # Imported here: status imports install, which imports add.
        from dotfiles.status import drifted
        paths, skipped = drifted(repo, host, root)
        for line in skipped:
            print(line)
        if not paths:
            print("nothing differs from the host")
            return
    if packages:
        have = host_packages.installed()
        if lacking := [name for name in packages if name not in have]:
            raise Error(f"not installed: {', '.join(lacking)}")
    try:
        copy(repo, host, paths, root, dry_run, force, as_template)
    finally:
        sudo.close()
    if packages:
        host_dir = repo / "hosts" / host
        listed = host_packages.read(host_dir)
        for name in dict.fromkeys(packages):
            print(f"{'unchanged' if name in listed else 'added'} package {name}")
        if not dry_run and not set(packages) <= set(listed):
            host_packages.write(host_dir, listed + packages)


def copy(repo: Path, host: str, paths: list[str], root: Path, dry_run: bool, force: bool,
         as_template: bool) -> None:
    for path in paths:
        if not path.startswith("/"):
            raise Error(f"not an absolute path: {path}")
        if path.lstrip("/") in OWN:
            raise Error(f"a host keeps its own {path.lstrip('/')} there: {path}")
        st_mode = mode_and_ids(root / path.lstrip("/")).mode
        for parent in reversed(PurePosixPath(path.lstrip("/")).parents[:-1]):
            if stat.S_ISLNK(mode_and_ids(root / parent).mode):
                raise Error(f"a symlink, not a directory: /{parent}")
        if not stat.S_ISREG(st_mode) and not stat.S_ISLNK(st_mode):
            raise Error(f"not a regular file: {path}")
        if path.endswith(SUFFIX):
            raise Error(f"a host reads a file ending in {SUFFIX} as a template: {path}")
        plain = f"hosts/{host}/{path.lstrip('/')}"
        link = symlink_on_the_way(repo / "hosts" / host, path.lstrip("/"))
        if link:
            raise Error(f"a symlink in the host, not a directory: hosts/{host}/{link};"
                        " dotfiles forget it first")
        if (repo / plain).is_dir() and not (repo / plain).is_symlink():
            raise Error(f"{plain} is a directory in the host; dotfiles forget its files first")
        if stat.S_ISLNK(st_mode):
            if as_template:
                raise Error(f"a symlink cannot be a template: {path}")
            if (repo / f"{plain}{SUFFIX}").exists():
                raise Error(f"{path} is kept as a template, {plain}{SUFFIX}; dotfiles forget it first")
            continue
        if as_template and (repo / plain).exists():
            raise Error(f"{path} is kept as a plain copy, {plain}; git rm it first")
        if not as_template and (repo / f"{plain}{SUFFIX}").exists():
            raise Error(f"{path} is kept as a template, {plain}{SUFFIX}; use --template")

    config = secrets.load(repo / "secret_leaks.toml")
    values_path = template.values_path(host)
    values = template.read_values(values_path)
    new_values: dict[str, str] = {}
    unnamed: dict[str, int] = {}  # path -> secrets left to name, in a dry run
    contents = {}
    links = {}  # path -> its target, for a symlink
    found = []
    for path in paths:
        src = root / path.lstrip("/")
        if stat.S_ISLNK(mode_and_ids(src).mode):  # A target is a path, not checked for secrets.
            try:
                links[path] = os.readlink(src)
            except PermissionError:
                links[path] = sudo.readlink(str(src))
            continue
        if not mode_and_ids(src).mode & 0o004:
            print(f"warning: {path} is closed to others; it may hold a secret, "
                  "check it before committing", file=sys.stderr)
        try:
            contents[path] = src.read_bytes()
        except PermissionError:
            contents[path] = sudo.read(str(src))
        if as_template:
            text, unnamed[path] = make_template(path, contents[path], config, values,
                                                new_values, ask=not dry_run)
            contents[path] = text.encode()
            found += secrets.report(path, secrets.find(config, text, path) if not unnamed[path] else [])
        else:
            found += secrets.report(path, secrets.find_secrets(config, contents[path], path))
    if found and as_template:
        raise Error("these still look like secrets in the template; make it by hand:\n  "
                    + "\n  ".join(found))
    if found and not force:
        raise Error("these look like secrets; keep the file as a template with --template, "
                    "or pass --force to copy it anyway:\n  " + "\n  ".join(found))
    if not dry_run:
        for name, value in new_values.items():
            template.save_value(values_path, name, value)
    for secret in found:
        print(f"warning: copying a secret: {secret}", file=sys.stderr)

    host_dir = repo / "hosts" / host
    meta_path = host_dir / ".meta"
    meta = read_meta(meta_path)
    old_meta = dict(meta)

    for path in paths:
        rel = path.lstrip("/")
        src = root / rel
        key = rel + SUFFIX if as_template else rel
        dest = host_dir / key
        if path in links:
            copy_link(dest, links[path], f"hosts/{host}/{key}", dry_run)
            if meta.pop(key, None) is not None:
                print(f"meta: removed {key}")
        else:
            st = mode_and_ids(src)
            git_mode = 0o755 if st.mode & 0o100 else 0o644
            copy_file(dest, contents[path], git_mode, unnamed.get(path, 0), f"hosts/{host}/{key}",
                      dry_run)
            update_meta(meta, key, st, git_mode)
        for parent in PurePosixPath(rel).parents[:-1]:
            update_meta(meta, f"{parent}/", mode_and_ids(root / parent, follow=True), 0o755)

    if meta != old_meta and not dry_run:
        write_meta(meta_path, meta)


def copy_link(dest: Path, target: str, name: str, dry_run: bool) -> None:
    """Makes dest a symlink to target, in place of what is there; prints the change."""
    if dest.is_symlink() and os.readlink(dest) == target:
        change = "unchanged"
    else:
        change = "updated" if dest.is_symlink() or dest.exists() else "added"
    print(f"{change} {name} -> {target}")
    if change != "unchanged" and not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)
        dest.symlink_to(target)


def copy_file(dest: Path, data: bytes, git_mode: int, unnamed: int, name: str,
              dry_run: bool) -> None:
    """Writes data to dest with git_mode, never through a symlink there;
    prints the change, and the values a template has left to name."""
    if dest.is_symlink():
        change = "updated"
    elif not dest.exists():
        change = "added"
    elif unnamed or dest.read_bytes() != data or dest.stat().st_mode & 0o777 != git_mode:
        change = "updated"
    else:
        change = "unchanged"
    left = f" ({unnamed} values to name)" if unnamed else ""
    print(f"{change} {name}{left}")
    if change != "unchanged" and not dry_run:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.unlink(missing_ok=True)  # a symlink there is replaced, not written through
        dest.write_bytes(data)
        dest.chmod(git_mode)


def write_meta(path: Path, meta: dict[str, str]) -> None:
    """Writes the lines of meta sorted by path, or removes path when there are none."""
    if meta:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(meta[key] + "\n" for key in sorted(meta)))
    else:
        path.unlink()


def update_meta(
    meta: dict[str, str], key: str, st: Stat, default_mode: int
) -> None:
    """Sets, keeps or removes the line for key, printing a change."""
    mode = st.mode & 0o7777
    owner = f"{user_name(st.uid)}:{group_name(st.gid)}"
    if mode == default_mode and owner == default_owner(key):
        if meta.pop(key, None) is not None:
            print(f"meta: removed {key}")
        return
    line = f"{mode:04o} {owner} {key}"
    if meta.get(key) != line:
        meta[key] = line
        print(f"meta: set {line}")


def make_template(path: str, data: bytes, config: secrets.Config, values: dict[str, str],
                  new_values: dict[str, str], ask: bool) -> tuple[str, int]:
    """data with each secret found in it replaced by its placeholder, and how
    many secrets are left without a name. A secret already in values takes
    its name; with ask, a new one is named by the user and goes into values
    and new_values, and without, it is left as it is and counted."""
    try:
        text = data.decode()
    except UnicodeDecodeError:
        raise Error(f"a template must be UTF-8 text: {path}") from None
    lines = text.splitlines()
    named = {value: name for name, value in reversed(values.items())}  # the first name wins
    unnamed = set()
    for line, rule, value in secrets.find_values(config, text, path):
        if not line or not value or value not in lines[line - 1]:
            raise Error(f"{path}:{line}: {rule}: the secret is not in the line as it is; "
                        "make the template by hand")
        if value in named:
            continue
        if not ask:
            unnamed.add(value)
            continue
        name = ask_name(f"{path}:{line}: {rule}", values)
        values[name] = new_values[name] = value
        named[value] = name
    for value in sorted(named.keys() - unnamed, key=len, reverse=True):
        text = text.replace(value, f"{{{{ {named[value]} }}}}")
    return text, len(unnamed)


def ask_name(where: str, values: dict[str, str]) -> str:
    """A name for the secret at where, asked until it is a free placeholder name."""
    if not sys.stdin.isatty():
        raise Error(f"{where}: the secret's name is asked in a terminal")
    while True:
        name = input(f"{where}, name for it: ").strip()
        if not template.PLACEHOLDER.fullmatch(f"{{{{ {name} }}}}"):
            print("a name is [a-z0-9_]", file=sys.stderr)
        elif name in values:
            print(f"{name} is taken by another value", file=sys.stderr)
        else:
            return name
