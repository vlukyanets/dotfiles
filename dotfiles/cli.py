"""The `dotfiles` command line."""

import argparse
import signal
import socket
import sys
from pathlib import Path

import tomli_w

from dotfiles import apply, config, feature
from dotfiles.errors import ConfigError
from dotfiles.layout import Layout, local_config, shown


def _where(args) -> tuple[str, Path, Path | None]:
    """(host, checkout, local config or None) that ARGS point the command at."""
    host = getattr(args, "host", None)
    source = args.source or (Layout.root if host else None)
    return host or socket.gethostname(), source or Layout.root, None if source else local_config()


def main() -> int:
    """Parse the command line and run the command; the exit status."""
    parser = argparse.ArgumentParser(prog="dotfiles")
    sub = parser.add_subparsers(dest="command", required=True)
    local = shown(local_config())
    p = sub.add_parser("init", help=f"write a host's resolved config to {local}")
    p.add_argument("name", nargs="?", default=socket.gethostname(), help="default: this machine")
    p.add_argument(
        "--source", type=Path, default=Layout.root, metavar="PATH", help="checkout to read"
    )
    p = sub.add_parser("config", help="print the resolved config of a host")
    p.add_argument("--host", help="a host of the checkout; default: this machine's config")
    p.add_argument("--explain", action="store_true", help="one line per key, with its file")
    sub.add_parser("check", help="resolve every host, and this machine's config")
    p = sub.add_parser("apply", help="this machine: packages, features, notices")
    p.add_argument("--dry-run", action="store_true", help="print what would change, no sudo")
    for name, p in sub.choices.items():
        if name != "init":  # init has its own, defaulting to this checkout
            p.add_argument(
                "--source",
                type=Path,
                metavar="PATH",
                help=f"read the config from hosts/ of this checkout, not {local}",
            )
    args = parser.parse_args()
    # The -> lines and the output of the commands they run, in order.
    sys.stdout.reconfigure(line_buffering=True)
    if args.source and not Layout(args.source).hosts.is_dir():
        print(f"error: {args.source}: not a dotfiles checkout (no hosts/)", file=sys.stderr)
        return 1

    try:
        if args.command == "check":
            results = apply.check(source=args.source)
            width = max(map(len, results))
            for host, error in results.items():
                print(f"{host:<{width}} {'ok' if error is None else 'FAIL'}")
                if error is not None:
                    print(f"error: {error}", file=sys.stderr)
            return 1 if any(results.values()) else 0
        if args.command == "init":
            print(
                config.init(args.name, source=args.source, checks=feature.checks())
                or "nothing to change"
            )
            return 0
        host, source, local = _where(args)
        if args.command == "config" and args.explain:
            sys.stdout.write(
                config.explain(host, local=local, source=source, checks=feature.checks())
            )
            return 0
        cfg = config.resolve(host, local=local, source=source, checks=feature.checks())
        if args.command == "apply":
            return apply.apply(host, dry_run=args.dry_run, cfg=cfg)
        sys.stdout.write(tomli_w.dumps(cfg))
    except ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 128 + signal.SIGINT  # the shell's status for a Ctrl-C
    return 0
