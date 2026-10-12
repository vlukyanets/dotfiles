"""dotfiles forget: removes files from nodes/<node>/, with their .meta lines.

A directory of the node left with no files goes too, with its line. The
machine is not touched: what install put there stays.
"""

import re
import shutil
from pathlib import Path, PurePosixPath

from dotfiles.add import OWN, Error, read_meta, write_meta
from dotfiles.template import SUFFIX


def forget(repo: Path, node: str, paths: list[str], dry_run: bool = False) -> None:
    """Removes each path's copy, or its template, from repo/nodes/<node>/.

    Prints each change; with dry_run, prints them and changes nothing.
    """
    node_dir = repo / "nodes" / node
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node) or not node_dir.is_dir():
        raise Error(f"no such node: {node}")
    keys = []
    for path in paths:
        rel = path.lstrip("/")
        key = next((key for key in (rel, rel + SUFFIX) if (node_dir / key).is_file()), None)
        if not path.startswith("/") or ".." in PurePosixPath(rel).parts or rel in OWN or not key:
            raise Error(f"not in node {node}: {path}")
        if key not in keys:
            keys.append(key)

    meta_path = node_dir / ".meta"
    meta = read_meta(meta_path)
    old_meta = dict(meta)
    for key in keys:
        print(f"removed nodes/{node}/{key}")
        if not dry_run:
            (node_dir / key).unlink()
        if meta.pop(key, None) is not None:
            print(f"meta: removed {key}")
    gone = {node_dir / key for key in keys}
    parents = {str(parent) for key in keys for parent in PurePosixPath(key).parents[:-1]}
    for parent in sorted(parents, reverse=True):  # a directory after those in it
        directory = node_dir / parent
        if any(not p.is_dir() and p not in gone for p in directory.rglob("*")):
            continue
        print(f"removed nodes/{node}/{parent}/")
        if not dry_run:
            shutil.rmtree(directory)  # Only the empty directories are left in it.
        if meta.pop(f"{parent}/", None) is not None:
            print(f"meta: removed {parent}/")
    if meta != old_meta and not dry_run:
        write_meta(meta_path, meta)
