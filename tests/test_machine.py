"""Tests for the machine operations and the sudo helper, on a fake filesystem."""

import base64
import io
import json
import os
import stat
from pathlib import Path
from typing import ClassVar

import pytest
from pyfakefs import helpers

from dotfiles import machine
from dotfiles.add import Error
from dotfiles.machine import Local, Stat, Sudo, serve

ROOT, ALICE = 0, 1000
PATH = "/d/a b ё"
BYTES = b"\xff\x00"


@pytest.fixture(autouse=True)
def fake(fs):
    """Root runs, as the sudo helper does; /d is an empty directory."""
    helpers.set_uid(ROOT)
    helpers.set_gid(ROOT)
    fs.create_dir("/d")
    yield
    helpers.reset_ids()


def ask(*requests):
    """The answers of serve to the requests, one JSON object per line."""
    lines = b"".join(json.dumps(r).encode() + b"\n" for r in requests)
    answers = io.BytesIO()
    serve(Local(), io.BytesIO(lines), answers)
    return [json.loads(line) for line in answers.getvalue().splitlines()]


def test_local_write_sets_contents_owner_and_mode():
    Local().write("/d/x", BYTES, 0o600, ALICE, ALICE)

    st = os.lstat("/d/x")
    assert Path("/d/x").read_bytes() == BYTES
    assert (st.st_mode & 0o777, st.st_uid, st.st_gid) == (0o600, ALICE, ALICE)
    assert os.listdir("/d") == ["x"]


def test_local_write_keeps_the_old_file_when_it_fails(monkeypatch):
    Path("/d/x").write_bytes(b"old")

    def refuse(*args):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chown", refuse)
    with pytest.raises(PermissionError):
        Local().write("/d/x", BYTES, 0o600, ALICE, ALICE)

    assert Path("/d/x").read_bytes() == b"old"
    assert os.listdir("/d") == ["x"]


def test_local_stat_of_a_missing_path_is_none():
    assert Local().stat("/d/missing") is None


def test_local_stat_follows_a_symlink_only_when_asked():
    Path(PATH).write_bytes(BYTES)
    os.symlink(PATH, "/d/link")
    assert stat.S_ISLNK(Local().stat("/d/link").mode)
    assert stat.S_ISREG(Local().stat("/d/link", follow=True).mode)


def test_serve_answers_each_operation():
    b64 = base64.b64encode(BYTES).decode()
    answers = ask(
        {"op": "stat", "path": PATH},
        {"op": "mkdir", "path": "/d/sub ё", "mode": 0o700, "uid": ALICE, "gid": ALICE},
        {"op": "write", "path": PATH, "data": b64, "mode": 0o600, "uid": ALICE, "gid": ALICE},
        {"op": "read", "path": PATH},
        {"op": "chmod", "path": PATH, "mode": 0o640},
        {"op": "chown", "path": PATH, "uid": ROOT, "gid": ROOT},
        {"op": "stat", "path": PATH},
    )

    assert answers[:3] == [{"ok": None}] * 3
    assert answers[3] == {"ok": b64}
    assert base64.b64decode(answers[3]["ok"]) == BYTES
    assert answers[4:6] == [{"ok": None}] * 2
    assert answers[6]["ok"] == {"mode": stat.S_IFREG | 0o640, "uid": ROOT, "gid": ROOT}
    assert os.lstat("/d/sub ё").st_mode & 0o777 == 0o700


def test_serve_answers_an_error():
    assert ask({"op": "read", "path": "/d/missing"}) == [
        {"error": "read /d/missing: No such file or directory"}
    ]


class FakePopen:
    """A sudo helper whose pipes run serve on the fake filesystem."""

    started: ClassVar[list[list[str]]] = []
    returncode = None

    def __init__(self, argv, stdin, stdout):
        self.started.append(argv)
        self.stdin = self
        self.stdout = io.BytesIO()

    def write(self, line):
        answers = io.BytesIO()
        serve(Local(), io.BytesIO(line), answers)
        self.stdout = io.BytesIO(self.stdout.read() + answers.getvalue())

    def flush(self):
        pass

    def close(self):
        pass

    def wait(self):
        return self.returncode


@pytest.fixture
def popen(monkeypatch):
    FakePopen.started = []
    monkeypatch.setattr(machine.subprocess, "Popen", FakePopen)
    return FakePopen


def test_sudo_starts_one_helper(popen):
    sudo = Sudo("/py")
    sudo.write(PATH, BYTES, 0o600, ALICE, ALICE)

    assert sudo.read(PATH) == BYTES
    assert sudo.stat(PATH) == Stat(stat.S_IFREG | 0o600, ALICE, ALICE)
    assert popen.started == [["sudo", "/py", "-I", "-B", "-m", "dotfiles.machine"]]


def test_sudo_raises_the_helpers_error(popen):
    with pytest.raises(Error, match="^read /d/missing: No such file or directory$"):
        Sudo("/py").read("/d/missing")


@pytest.mark.parametrize("closed", ["stdout", "stdin"])
def test_sudo_raises_when_the_helper_exits(monkeypatch, closed):
    """The password prompt is cancelled: no answer, or no one to ask."""

    class Dead(FakePopen):
        returncode = 1

        def write(self, line):
            if closed == "stdin":
                raise BrokenPipeError()

    monkeypatch.setattr(machine.subprocess, "Popen", Dead)
    with pytest.raises(Error, match="^sudo helper exited with 1$"):
        Sudo("/py").stat("/d")


def test_sudo_close_after_the_helper_died(monkeypatch):
    """close() in a finally must not hide the Error with a BrokenPipeError."""

    class Dead(FakePopen):
        returncode = 1

        def write(self, line):
            raise BrokenPipeError()

        def close(self):
            raise BrokenPipeError()

    monkeypatch.setattr(machine.subprocess, "Popen", Dead)
    sudo = Sudo("/py")
    with pytest.raises(Error, match="^sudo helper exited with 1$"):
        sudo.stat("/d")
    sudo.close()
    assert sudo.helper is None
