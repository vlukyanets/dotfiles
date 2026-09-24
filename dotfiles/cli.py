"""The `dotfiles` command line."""

import argparse
import socket
import sys
from pathlib import Path

import tomli_w

from dotfiles import apply, config, render
from dotfiles.config import ROOT

SOURCE = "read the config from hosts/ of this checkout, not ~/.config/dotfiles"


def where(args) -> tuple[str, Path, Path | None]:
    """The host, the checkout its config comes from and the machine config
    to read instead (None with --source or --host). The templates always
    come from ROOT."""
    host = getattr(args, "host", None)
    source = args.source or (ROOT if host else None)
    return host or socket.gethostname(), source or ROOT, None if source else config.local_path()


def main() -> int:
    parser = argparse.ArgumentParser(prog="dotfiles")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("init", help="write a host's resolved config to ~/.config/dotfiles")
    p.add_argument("name", nargs="?", default=socket.gethostname(), help="default: this machine")
    p.add_argument("--source", type=Path, default=ROOT, metavar="PATH", help="checkout to read")
    p = sub.add_parser("config", help="print the resolved config of a host")
    p.add_argument("--host", help="a host of the checkout; default: this machine's config")
    p.add_argument("--explain", action="store_true", help="one line per key, with its file")
    p = sub.add_parser("render", help="write a host's home tree into a directory")
    p.add_argument("--host", help="a host of the checkout; default: this machine's config")
    p.add_argument("--out", type=Path, required=True, help="missing or empty directory")
    p.add_argument("--current", type=Path, help="home whose files merged templates read")
    p = sub.add_parser("deploy", help="write this machine's dotfiles into $HOME where they differ")
    p.add_argument("--dry-run", action="store_true", help="print what would change, write nothing")
    sub.add_parser("check", help="resolve and render every host, and this machine's config")
    p = sub.add_parser("apply", help="this machine: features, dotfiles, notices")
    p.add_argument("--dry-run", action="store_true", help="print what would change, no sudo")
    for name, p in sub.choices.items():
        if name != "init":  # init has its own, defaulting to this checkout
            p.add_argument("--source", type=Path, metavar="PATH", help=SOURCE)
    args = parser.parse_args()
    # The -> lines and the output of the commands they run, in order.
    sys.stdout.reconfigure(line_buffering=True)
    if args.source and not (args.source / "hosts").is_dir():
        print(f"error: {args.source}: not a dotfiles checkout (no hosts/)", file=sys.stderr)
        return 1

    if args.command == "check":
        results = render.check(source=args.source)
        for host, error in results.items():
            print(f"{host:<14} {'ok' if error is None else 'FAIL'}")
            if error is not None:
                print(f"error: {error}", file=sys.stderr)
        return 1 if any(results.values()) else 0

    try:
        if args.command == "init":
            print(config.init(args.name, args.source) or "nothing to change")
            return 0
        host, source, local = where(args)
        if args.command == "config" and args.explain:
            sys.stdout.write(config.explain(host, source, local))
            return 0
        cfg = config.resolve(host, source, local)
        if args.command == "apply":
            return apply.apply(host, dry_run=args.dry_run, cfg=cfg)
        if args.command == "deploy":
            lines = render.deploy(host, dry_run=args.dry_run, cfg=cfg)
            print("\n".join(lines) or "nothing to change")
        elif args.command == "render":
            render.render(host, args.out, current=args.current, cfg=cfg)
        else:
            sys.stdout.write(tomli_w.dumps(cfg))
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0
