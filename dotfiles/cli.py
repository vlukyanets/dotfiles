"""The dotfiles command."""

import argparse
import os
import sys
from pathlib import Path

from dotfiles.add import Error, add

REPO = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dotfiles")
    commands = parser.add_subparsers(dest="command", required=True)

    add_parser = commands.add_parser(
        "add", help="copy machine files into nodes/<node>/ and update its .meta"
    )
    add_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    add_parser.add_argument(
        "--force", action="store_true", help="copy files even if they look like they hold a secret"
    )
    add_parser.add_argument(
        "--root", type=Path, default=Path("/"), help="read the files from ROOT instead of /"
    )
    add_parser.add_argument("node", help="the node's name, as in nodes/<node>/")
    add_parser.add_argument("paths", nargs="+", metavar="path", help="an absolute path on the machine")

    args = parser.parse_args(argv)
    try:
        if os.geteuid() == 0:
            raise Error("run as your user; the files read through sudo when needed")
        add(REPO, args.node, args.paths, root=args.root, dry_run=args.dry_run, force=args.force)
    except Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0
