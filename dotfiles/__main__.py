import argparse
import socket
import sys
from pathlib import Path

import tomli_w

from dotfiles import apply, config, render


def main() -> int:
    parser = argparse.ArgumentParser(prog="dotfiles")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("config", help="print the resolved config of a host")
    p.add_argument("--host", default=socket.gethostname(), help="default: this machine")
    p.add_argument("--explain", action="store_true", help="one line per key, with its file")
    p = sub.add_parser("render", help="write a host's home tree into a directory")
    p.add_argument("--host", default=socket.gethostname(), help="default: this machine")
    p.add_argument("--out", type=Path, required=True, help="missing or empty directory")
    p.add_argument("--current", type=Path, help="home whose files merged templates read")
    p = sub.add_parser("deploy", help="write this machine's dotfiles into $HOME where they differ")
    p.add_argument("--dry-run", action="store_true", help="print what would change, write nothing")
    sub.add_parser("check", help="resolve and render every host in hosts/ and one unknown host")
    p = sub.add_parser("apply", help="this machine: features, dotfiles, notices")
    p.add_argument("--dry-run", action="store_true", help="print what would change, no sudo")
    args = parser.parse_args()
    # The -> lines and the output of the commands they run, in order.
    sys.stdout.reconfigure(line_buffering=True)

    if args.command == "check":
        results = render.check()
        for host, error in results.items():
            print(f"{host:<14} {'ok' if error is None else 'FAIL'}")
            if error is not None:
                print(f"error: {error}", file=sys.stderr)
        return 1 if any(results.values()) else 0

    try:
        if args.command == "apply":
            return apply.apply(socket.gethostname(), dry_run=args.dry_run)
        if args.command == "deploy":
            for line in render.deploy(socket.gethostname(), dry_run=args.dry_run):
                print(line)
        elif args.command == "render":
            render.render(args.host, args.out, current=args.current)
        elif args.explain:
            sys.stdout.write(config.explain(args.host))
        else:
            sys.stdout.write(tomli_w.dumps(config.resolve(args.host)))
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    sys.exit(main())
