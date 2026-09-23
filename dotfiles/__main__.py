import argparse
import socket
import sys

import tomli_w

from dotfiles import config


def main() -> int:
    parser = argparse.ArgumentParser(prog="dotfiles")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("config", help="print the resolved config of a host")
    p.add_argument("--host", default=socket.gethostname(), help="default: this machine")
    sub.add_parser("check", help="resolve every host in hosts/ and one unknown host")
    args = parser.parse_args()

    if args.command == "check":
        results = config.check()
        for host, error in results.items():
            print(f"{host:<14} {'ok' if error is None else 'FAIL'}")
            if error is not None:
                print(f"error: {error}", file=sys.stderr)
        return 1 if any(results.values()) else 0

    try:
        sys.stdout.write(tomli_w.dumps(config.resolve(args.host)))
    except config.ConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
