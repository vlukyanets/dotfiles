"""dotfiles new: makes a host, hosts/<host>/, with an empty .meta.

The empty .meta keeps the directory in git, which keeps no empty one, and
changes nothing: it lists no file off the defaults.
"""

from pathlib import Path

from dotfiles.add import HOST_NAME, Error


def new(repo: Path, host: str, dry_run: bool = False) -> None:
    """Makes repo/hosts/<host>/ with an empty .meta, unless the host exists.

    Prints the change; with dry_run, prints it and changes nothing.
    """
    if not HOST_NAME.fullmatch(host):
        raise Error(f"bad host name: {host}")
    host_dir = repo / "hosts" / host
    if host_dir.is_dir():
        print(f"unchanged hosts/{host}/")
        return
    print(f"added hosts/{host}/.meta")
    if not dry_run:
        host_dir.mkdir(parents=True)
        (host_dir / ".meta").touch()
