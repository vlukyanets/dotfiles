"""The root side of engine._Root: runs what the apply sends until it hangs up.

Started as `SUDO_CMD python -I root.py SOCKET`, so it imports only the stdlib.
"""

import signal
import socket
import subprocess
import sys
from multiprocessing.connection import Connection


def _serve(address: str) -> None:
    """Each (argv, kwargs) from ADDRESS run, its CompletedProcess or exception sent back."""
    sock = socket.socket(socket.AF_UNIX)
    sock.connect(address)
    conn = Connection(sock.detach())
    while True:
        try:
            argv, kwargs = conn.recv()
        except EOFError:
            return
        try:
            result = subprocess.run(argv, text=True, **kwargs)  # noqa: PLW1510 — check is in kwargs
        except Exception as error:  # noqa: BLE001 — CalledProcessError, FileNotFoundError: raised by the caller
            result = error
        conn.send(result)


if __name__ == "__main__":
    try:
        _serve(sys.argv[1])
    except KeyboardInterrupt:
        sys.exit(128 + signal.SIGINT)  # the shell's status for a Ctrl-C
