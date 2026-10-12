"""The dotfiles command."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from dotfiles import secrets
from dotfiles.add import Error, add
from dotfiles.cleanup import cleanup
from dotfiles.init import URL, find_repo, init
from dotfiles.install import install
from dotfiles.restore import restore
from dotfiles.status import status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dotfiles")
    commands = parser.add_subparsers(dest="command", required=True)

    add_parser = commands.add_parser(
        "add", help="copy machine files into nodes/<node>/ and update its .meta"
    )
    add_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    copying = add_parser.add_mutually_exclusive_group()
    copying.add_argument(
        "--force", action="store_true", help="copy files even if they look like they hold a secret"
    )
    copying.add_argument(
        "--template", action="store_true",
        help="keep each file as a template, naming the secrets found in it",
    )
    add_parser.add_argument(
        "--root", type=Path, default=Path("/"), help="read the files from ROOT instead of /"
    )
    add_parser.add_argument("node", help="the node's name, as in nodes/<node>/")
    add_parser.add_argument("paths", nargs="+", metavar="path", help="an absolute path on the machine")

    install_parser = commands.add_parser(
        "install", help="put nodes/<node>/ onto the machine, with its owners and modes"
    )
    install_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    install_parser.add_argument(
        "--root", type=Path, default=Path("/"), help="install under ROOT instead of /"
    )
    install_parser.add_argument("node", help="the node's name, as in nodes/<node>/")

    restore_parser = commands.add_parser(
        "restore", help="put back the files a run of install replaced, from .backups/<node>/"
    )
    restore_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    restore_parser.add_argument(
        "--root", type=Path, default=Path("/"), help="restore under ROOT instead of /"
    )
    restore_parser.add_argument("node", help="the node's name, as in .backups/<node>/")
    restore_parser.add_argument(
        "backup", nargs="*", metavar="run|path",
        help="the run, as in .backups/<node>/<run>/, the last one if none is given;"
             " then the absolute paths to put back, all of them if none is given",
    )

    init_parser = commands.add_parser(
        "init", help="clone the repository for an installed command, as chezmoi does"
    )
    init_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    init_parser.add_argument("url", nargs="?", default=URL, help=f"the repository, {URL} by default")

    status_parser = commands.add_parser(
        "status", help="show what on the machine differs from nodes/<node>/"
    )
    status_parser.add_argument(
        "-v", "--verbose", action="store_true", help="show a diff of each modified file"
    )
    status_parser.add_argument(
        "--root", type=Path, default=Path("/"), help="compare ROOT instead of /"
    )
    status_parser.add_argument("node", help="the node's name, as in nodes/<node>/")

    cleanup_parser = commands.add_parser(
        "cleanup", help="remove the backups dotfiles install keeps in .backups/"
    )
    cleanup_parser.add_argument("--dry-run", action="store_true", help="print the changes, make none")
    which = cleanup_parser.add_mutually_exclusive_group()
    which.add_argument("--keep", type=int, metavar="N", help="keep the last N runs of each node")
    which.add_argument("--older-than", type=int, metavar="DAYS", help="remove only runs older than DAYS")

    scan_parser = commands.add_parser(
        "scan", help="find what looks like a secret, by the rules in secret_leaks.toml"
    )
    what = scan_parser.add_mutually_exclusive_group(required=True)
    what.add_argument("--staged", action="store_true", help="scan the lines the staged changes add")
    what.add_argument("--history", action="store_true", help="scan the lines every commit adds")
    what.add_argument("paths", nargs="*", default=[], type=Path, metavar="path",
                      help="a file, or a directory to scan file by file")

    args = parser.parse_args(argv)
    try:
        if args.command == "init":
            init(args.url, dry_run=args.dry_run)
            return 0
        repo = find_repo()
        if args.command == "scan":
            return scan(args, repo)
        if os.geteuid() == 0:
            raise Error("run as your user; sudo is used when needed")
        if args.command == "add":
            add(repo, args.node, args.paths, root=args.root, dry_run=args.dry_run, force=args.force,
                as_template=args.template)
        elif args.command == "install":
            install(repo, args.node, root=args.root, dry_run=args.dry_run)
        elif args.command == "restore":
            runs = [arg for arg in args.backup if not arg.startswith("/")]
            if len(runs) > 1:
                raise Error(f"one run at most: {' '.join(runs)}")
            restore(repo, args.node, runs[0] if runs else None,
                    [arg for arg in args.backup if arg.startswith("/")],
                    root=args.root, dry_run=args.dry_run)
        elif args.command == "status":
            status(repo, args.node, root=args.root, verbose=args.verbose)
        else:
            cleanup(repo, keep=args.keep, older_than=args.older_than, dry_run=args.dry_run)
    except Error as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


def scan(args: argparse.Namespace, repo: Path) -> int:
    config = secrets.load(repo / "secret_leaks.toml")
    if args.staged or args.history:
        try:
            findings = (secrets.scan_staged if args.staged else secrets.scan_history)(config, repo)
        except subprocess.CalledProcessError as e:
            print(f"error: git: {e.stderr.strip()}", file=sys.stderr)
            return 2
    else:
        missing = [str(path) for path in args.paths if not path.exists()]
        if missing:
            print(f"error: no such file: {', '.join(missing)}", file=sys.stderr)
            return 2
        findings = secrets.scan_paths(config, args.paths)
    if not findings:
        return 0
    print("these look like secrets; keep the file as a template, or mark a line"
          " that holds none with secret-leaks:allow:", file=sys.stderr)
    for finding in findings:
        print(f"  {finding}", file=sys.stderr)
    return 1
