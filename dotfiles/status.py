"""dotfiles status: what on the machine differs from hosts/<host>/, like git status.

The host is the index and the machine the working tree: each arrow goes
from what the host has to what the machine has. Nothing is written.
"""

import difflib
from pathlib import Path

from dotfiles import install, packages
from dotfiles.install import Item, host_dir_of, owner_text, survey
from dotfiles.template import SUFFIX, names, read_values, text_of, values_path


def status(repo: Path, host: str, root: Path = Path("/"), verbose: bool = False) -> None:
    """Prints what differs; with verbose, a diff of each modified file too."""
    host_dir = host_dir_of(repo, host, root)
    try:
        values = read_values(values_path(host))
        items = survey(host_dir, root, values)
    finally:
        install.sudo.close()
    lacking = packages.missing(host_dir) if str(root) == "/" else []
    extra = packages.extra(host_dir) if str(root) == "/" else []

    changed: list[tuple[str, str]] = []
    dirs: list[tuple[str, str]] = []
    modified: list[Item] = []
    for item in items:
        is_dir = item.key.endswith("/")
        if item.st is None:
            if not is_dir:  # A missing directory shows as its missing files.
                changed.append(("missing", item.path))
            continue
        label = f"{item.path}/" if is_dir else item.path
        if item.link is not None or item.machine_link is not None:
            if item.link != item.machine_link:  # A symlink's owner and mode are never compared.
                host_side, machine_side = item.link or "(a file)", item.machine_link or "(a file)"
                changed.append(("target", f"{label}  {host_side} → {machine_side}"))
            continue
        lines = dirs if is_dir and not item.in_meta else changed
        if item.missing:
            changed.append(("unfilled", f"{label}  ({', '.join(item.missing)})"))
        elif not is_dir and item.machine_data != item.data:
            changed.append(("modified", label))
            modified.append(item)
        mode, uid, gid = item.st.mode & 0o7777, item.st.uid, item.st.gid
        if (uid, gid) != (item.uid, item.gid):
            lines.append(("owner", f"{label}  {owner_text(item.uid, item.gid)} → {owner_text(uid, gid)}"))
        if mode != item.mode:
            lines.append(("mode", f"{label}  {item.mode:04o} → {mode:04o}"))

    print(f"Host {host}, root {root}")
    if not changed and not dirs and not lacking and not extra:
        print("Nothing differs from the host.")
    if changed:
        print(f"\nChanges on the machine:\n"
              f"  (dotfiles add --host {host} <path> keeps them; dotfiles install --host {host} undoes them)")
        print_lines(changed)
    if lacking:
        print(f"\nPackages the machine lacks:\n"
              f"  (dotfiles install --host {host} installs them;"
              f" dotfiles forget --host {host} --package <name> drops them)")
        print_lines([("package", name) for name in lacking])
    if extra:
        print(f"\nPackages not in the host:\n"
              f"  (dotfiles add --host {host} --package <name> keeps them; removing them is yours)")
        print_lines([("package", name) for name in extra])
    if dirs:
        print("\nDirectories off their defaults, with no .meta line:\n"
              "  (dotfiles add records them with the next file added under them)")
        print_lines(dirs)
    if verbose:
        for item in modified:
            print()
            print_diff(f"hosts/{host}/{item.key}", item, host_dir, values)


def print_lines(lines: list[tuple[str, str]]) -> None:
    for kind, text in lines:
        print(f"        {kind + ':':<11}{text}")


def print_diff(name: str, item: Item, host_dir: Path, values: dict[str, str]) -> None:
    """A unified diff from the host's file to the machine's. For a template,
    from the template as it is to the machine's file with each of its values
    put back as its placeholder, so no value it knows is shown."""
    try:
        old, new = item.data.decode(), item.machine_data.decode()
    except UnicodeDecodeError:
        old = new = "\0"
    if "\0" in old + new:
        print(f"Binary files {name} and {item.path} differ")
        return
    machine = item.path
    if item.key.endswith(SUFFIX):
        old = text_of(host_dir / item.key)
        # The longest first, so a value inside another one is not put back alone.
        for placeholder in sorted(names(old), key=lambda n: len(values[n]), reverse=True):
            if values[placeholder]:
                new = new.replace(values[placeholder], f"{{{{ {placeholder} }}}}")
        machine += " (values hidden)"
    for line in difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                     name, machine):
        print(line, end="" if line.endswith("\n") else "\n\\ No newline at end of file\n")


def drifted(repo: Path, host: str, root: Path = Path("/")) -> tuple[list[str], list[str]]:
    """The paths, from /, of the files and symlinks of the host that changed
    on the machine and that add can take back as they are; and a line for
    each change it cannot: a file missing on the machine, or a template."""
    host_dir = host_dir_of(repo, host, root)
    try:
        items = survey(host_dir, root, read_values(values_path(host)))
    finally:
        install.sudo.close()
    paths: list[str] = []
    skipped: list[str] = []
    for item in items:
        if item.key.endswith("/"):
            continue
        path = "/" + item.key.removesuffix(SUFFIX)
        if item.st is None:
            skipped.append(f"skipped {path}: missing on the machine; dotfiles forget {host} {path} drops it")
        elif not differs(item):
            continue
        elif item.key.endswith(SUFFIX):
            skipped.append(f"skipped {path}: a template; dotfiles add --template {host} {path} remakes it")
        else:
            paths.append(path)
    return paths, skipped


def differs(item: Item) -> bool:
    """Whether the machine's file or symlink at item's path differs from the host's."""
    st = item.st
    assert st is not None  # Only a path the machine has is compared.
    if item.link is not None or item.machine_link is not None:
        return item.link != item.machine_link  # A symlink's owner and mode are never compared.
    return (bool(item.missing) or item.machine_data != item.data
            or (st.uid, st.gid) != (item.uid, item.gid) or st.mode & 0o7777 != item.mode)
