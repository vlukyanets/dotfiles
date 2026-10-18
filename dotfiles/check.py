"""dotfiles check: finds what would stop install in each host, without a machine.

It reads only the repository, so it runs anywhere, as any user: in CI and
in the pre-commit hook. Problems of the machine are install's to find.
"""

from pathlib import Path

from dotfiles.add import HOST_NAME
from dotfiles.install import read_host
from dotfiles.machine import Error


def check(repo: Path, hosts: list[str]) -> int:
    """Prints `<host>: ok`, or the host and each of its problems indented,
    for each of hosts, or every host when none is named; 1 when a host has
    a problem, 0 otherwise."""
    hosts_dir = repo / "hosts"
    if not hosts:
        hosts = sorted(p.name for p in hosts_dir.iterdir() if p.is_dir()) if hosts_dir.is_dir() else []
        if not hosts:
            print("no hosts to check")
            return 0
    code = 0
    for host in hosts:
        if not HOST_NAME.fullmatch(host):
            print(f"{host}: bad host name")
        elif not (hosts_dir / host).is_dir():
            print(f"{host}: no such host")
        else:
            try:
                read_host(hosts_dir / host)
            except Error as e:
                print(f"{host}:\n  {e}")
            else:
                print(f"{host}: ok")
                continue
        code = 1
    return code
