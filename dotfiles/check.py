"""dotfiles check: finds what would stop install in each node, without a machine.

It reads only the repository, so it runs anywhere, as any user: in CI and
in the pre-commit hook. Problems of the machine are install's to find.
"""

import re
from pathlib import Path

from dotfiles.install import read_node
from dotfiles.machine import Error


def check(repo: Path, nodes: list[str]) -> int:
    """Prints `<node>: ok`, or the node and each of its problems indented,
    for each of nodes, or every node when none is named; 1 when a node has
    a problem, 0 otherwise."""
    nodes_dir = repo / "nodes"
    if not nodes:
        nodes = sorted(p.name for p in nodes_dir.iterdir() if p.is_dir()) if nodes_dir.is_dir() else []
        if not nodes:
            print("no nodes to check")
            return 0
    code = 0
    for node in nodes:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", node):
            print(f"{node}: bad node name")
        elif not (nodes_dir / node).is_dir():
            print(f"{node}: no such node")
        else:
            try:
                read_node(nodes_dir / node)
            except Error as e:
                print(f"{node}:\n  {e}")
            else:
                print(f"{node}: ok")
                continue
        code = 1
    return code
