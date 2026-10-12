"""The operations on a machine's files, and the sudo helper that runs them.

Local does each operation as the current user. Sudo has the same methods and
sends them to `python -m dotfiles.machine` running under sudo, which answers
them with serve(): one JSON object per line in, one per line out.
"""

import base64
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from typing import BinaryIO


class Error(Exception):
    """A problem with the input or the machine, reported to the user."""


@dataclass(frozen=True)
class Stat:
    mode: int  # st_mode, the file type bits included
    uid: int
    gid: int


class Local:
    def stat(self, path: str, follow: bool = False) -> Stat | None:
        """Without follow, a symlink is not followed."""
        try:
            st = os.stat(path, follow_symlinks=follow)
        except FileNotFoundError:
            return None
        return Stat(st.st_mode, st.st_uid, st.st_gid)

    def read(self, path: str) -> bytes:
        with open(path, "rb") as f:
            return f.read()

    def mkdir(self, path: str, mode: int, uid: int, gid: int) -> None:
        os.mkdir(path)
        os.chown(path, uid, gid)
        os.chmod(path, mode)  # after mkdir, so the umask does not change it

    def write(self, path: str, data: bytes, mode: int, uid: int, gid: int) -> None:
        """Replaces path with a file made beside it, so a failure leaves the old one."""
        fd, temp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".dotfiles-")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.chown(temp, uid, gid)  # before the mode: chown clears setuid
            os.chmod(temp, mode)
            os.replace(temp, path)
        except BaseException:
            os.unlink(temp)
            raise

    def readlink(self, path: str) -> str:
        return os.readlink(path)

    def symlink(self, path: str, target: str, uid: int, gid: int) -> None:
        """Replaces path with a symlink made beside it, as write does a file."""
        temp = os.path.join(os.path.dirname(path), f".dotfiles-{os.urandom(8).hex()}")
        os.symlink(target, temp)
        try:
            os.chown(temp, uid, gid, follow_symlinks=False)
            os.replace(temp, path)
        except BaseException:
            os.unlink(temp)
            raise

    def chmod(self, path: str, mode: int) -> None:
        os.chmod(path, mode)

    def chown(self, path: str, uid: int, gid: int) -> None:
        os.chown(path, uid, gid)


def serve(machine: Local, requests: BinaryIO, answers: BinaryIO) -> None:
    """Answers each request line until requests ends."""
    for line in requests:
        request = json.loads(line)
        op = request.pop("op")
        if "data" in request:
            request["data"] = base64.b64decode(request["data"])
        try:
            result = getattr(machine, op)(**request)
            if isinstance(result, bytes):
                result = base64.b64encode(result).decode()
            elif isinstance(result, Stat):
                result = asdict(result)
            answer = {"ok": result}
        except OSError as e:
            answer = {"error": f"{op} {request['path']}: {e.strerror}"}
        answers.write(json.dumps(answer).encode() + b"\n")
        answers.flush()


class Sudo:
    """The Local methods, run by one helper process under sudo."""

    def __init__(self, python: str = sys.executable):
        self.python = python
        self.helper: subprocess.Popen | None = None

    def call(self, op: str, **args):
        if self.helper is None:
            self.helper = subprocess.Popen(
                ["sudo", self.python, "-I", "-B", "-m", "dotfiles.machine"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
            )
        if "data" in args:
            args["data"] = base64.b64encode(args["data"]).decode()
        line = json.dumps({"op": op, **args}).encode() + b"\n"
        assert self.helper.stdin and self.helper.stdout  # Both are pipes, so never None.
        try:
            self.helper.stdin.write(line)
            self.helper.stdin.flush()
            answer = self.helper.stdout.readline()
        except BrokenPipeError:  # the helper is gone: sudo failed or was cancelled
            answer = b""
        if not answer:
            raise Error(f"sudo helper exited with {self.helper.wait()}")
        answer = json.loads(answer)
        if "error" in answer:
            raise Error(answer["error"])
        return answer["ok"]

    def stat(self, path: str, follow: bool = False) -> Stat | None:
        result = self.call("stat", path=path, follow=follow)
        return None if result is None else Stat(**result)

    def read(self, path: str) -> bytes:
        return base64.b64decode(self.call("read", path=path))

    def mkdir(self, path: str, mode: int, uid: int, gid: int) -> None:
        self.call("mkdir", path=path, mode=mode, uid=uid, gid=gid)

    def write(self, path: str, data: bytes, mode: int, uid: int, gid: int) -> None:
        self.call("write", path=path, data=data, mode=mode, uid=uid, gid=gid)

    def readlink(self, path: str) -> str:
        return self.call("readlink", path=path)

    def symlink(self, path: str, target: str, uid: int, gid: int) -> None:
        self.call("symlink", path=path, target=target, uid=uid, gid=gid)

    def chmod(self, path: str, mode: int) -> None:
        self.call("chmod", path=path, mode=mode)

    def chown(self, path: str, uid: int, gid: int) -> None:
        self.call("chown", path=path, uid=uid, gid=gid)

    def close(self) -> None:
        if self.helper is not None:
            try:
                if self.helper.stdin:
                    self.helper.stdin.close()
            except BrokenPipeError:  # the helper is gone; its unsent bytes are moot
                pass
            self.helper.wait()
            self.helper = None


if __name__ == "__main__":
    serve(Local(), sys.stdin.buffer, sys.stdout.buffer)
