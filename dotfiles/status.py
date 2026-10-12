"""dotfiles status: what on the machine differs from nodes/<node>/, like git status.

The node is the index and the machine the working tree: each arrow goes
from what the node has to what the machine has. Nothing is written.
"""

import difflib
from pathlib import Path

from dotfiles import install, packages
from dotfiles.install import Item, node_dir_of, owner_text, survey
from dotfiles.template import SUFFIX, names, read_values, text_of, values_path


def status(repo: Path, node: str, root: Path = Path("/"), verbose: bool = False) -> None:
    """Prints what differs; with verbose, a diff of each modified file too."""
    node_dir = node_dir_of(repo, node, root)
    try:
        values = read_values(values_path(node))
        items = survey(node_dir, root, values)
    finally:
        install.sudo.close()
    lacking = packages.missing(node_dir) if str(root) == "/" else []

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

    print(f"Node {node}, root {root}")
    if not changed and not dirs and not lacking:
        print("Nothing differs from the node.")
    if changed:
        print(f"\nChanges on the machine:\n"
              f"  (dotfiles add {node} <path> keeps them; dotfiles install {node} undoes them)")
        print_lines(changed)
    if lacking:
        print(f"\nPackages the machine lacks:\n"
              f"  (dotfiles install {node} installs them;"
              f" dotfiles forget {node} --package <name> drops them)")
        print_lines([("package", name) for name in lacking])
    if dirs:
        print("\nDirectories off their defaults, with no .meta line:\n"
              "  (dotfiles add records them with the next file added under them)")
        print_lines(dirs)
    if verbose:
        for item in modified:
            print()
            print_diff(f"nodes/{node}/{item.key}", item, node_dir, values)


def print_lines(lines: list[tuple[str, str]]) -> None:
    for kind, text in lines:
        print(f"        {kind + ':':<11}{text}")


def print_diff(name: str, item: Item, node_dir: Path, values: dict[str, str]) -> None:
    """A unified diff from the node's file to the machine's. For a template,
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
        old = text_of(node_dir / item.key)
        # The longest first, so a value inside another one is not put back alone.
        for placeholder in sorted(names(old), key=lambda n: len(values[n]), reverse=True):
            if values[placeholder]:
                new = new.replace(values[placeholder], f"{{{{ {placeholder} }}}}")
        machine += " (values hidden)"
    for line in difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                     name, machine):
        print(line, end="" if line.endswith("\n") else "\n\\ No newline at end of file\n")
