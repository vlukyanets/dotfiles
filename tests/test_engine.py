import subprocess

import pytest

from dotfiles import engine
from dotfiles.engine import (
    Deferred,
    Failed,
    Skip,
    as_root,
    defer,
    die,
    notice,
    os_guard,
    output,
    print_notices,
    retry,
    run,
)


class Fake:
    """Stands in for engine._run: answers from ANSWERS (argv tuple -> (rc,
    stdout)), 0 and "" otherwise, and records every argv in CALLS."""

    def __init__(self):
        self.answers: dict[tuple, tuple[int, str]] = {}
        self.calls: list[list[str]] = []

    def __call__(self, argv, check=False, **kwargs):
        self.calls.append(argv)
        rc, out = self.answers.get(tuple(argv), (0, ""))
        if rc and check:
            raise subprocess.CalledProcessError(rc, argv)
        return subprocess.CompletedProcess(argv, rc, out, "")


@pytest.fixture
def fake(monkeypatch) -> Fake:
    fake = Fake()
    monkeypatch.setattr(engine, "_run", fake)
    return fake


def test_as_root_prefix(fake, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo -n")
    as_root("true")
    monkeypatch.setenv("DOTFILES_SNAPPER_STATE", "/run/x")
    as_root("true")
    monkeypatch.setenv("SUDO_CMD", "")
    as_root("true")
    monkeypatch.setattr(engine.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_CMD", "sudo")
    as_root("true")
    assert fake.calls == [
        ["sudo", "-n", "true"],
        ["sudo", "-n", "--preserve-env=SNAP_PAC_SKIP,DOTFILES_SNAPPER_STATE", "true"],
        ["true"],
        ["true"],
    ]


def test_sudo_from_conftest_fails():
    with pytest.raises(subprocess.CalledProcessError):
        as_root("true")


def test_mutations_must_succeed(fake):
    fake.answers[("false",)] = (1, "")
    with pytest.raises(subprocess.CalledProcessError):
        run("false")


def test_dry_run_runs_nothing(fake, monkeypatch):
    monkeypatch.setattr(engine, "DRY_RUN", True)
    as_root("rm", "-rf", "/")
    run("touch", "x")
    assert fake.calls == []


def test_output():
    assert output("printf", "a\\nb\\n") == "a\nb"
    assert output("sh", "-c", "echo disabled; exit 1") == "disabled"
    assert output("no-such-command-here") is None


def test_retry(monkeypatch, capsys):
    slept = []
    monkeypatch.setattr(engine, "sleep", slept.append)
    attempts = []

    def flaky(n):
        attempts.append(n)
        if len(attempts) < n:
            raise subprocess.CalledProcessError(1, "x")

    assert retry(flaky, 2) is True
    assert attempts == [2, 2] and slept == [10]
    attempts.clear()
    assert retry(flaky, 9) is False
    assert len(attempts) == 3 and slept == [10, 10, 20]
    assert "warning: 9 failed (attempt 2/3), retrying in 20s" in capsys.readouterr().err


def test_die_defer_os_guard(monkeypatch):
    with pytest.raises(Failed, match="^boom$"):
        die("boom")
    with pytest.raises(Deferred, match="^net$"):
        defer("net")
    release = {"ID": "cachyos", "ID_LIKE": "arch"}
    monkeypatch.setattr(engine.platform, "freedesktop_os_release", lambda: release)
    os_guard("arch")
    os_guard("darwin", "linux")
    with pytest.raises(Skip):
        os_guard("darwin", "debian")


def test_notices_now_and_at_the_end(capsys):
    notice("log out and back in")
    assert capsys.readouterr().err == "warning: log out and back in\n"
    print_notices()
    assert capsys.readouterr().out == "\nNotices from this apply:\n    log out and back in\n"
    print_notices()
    assert capsys.readouterr().out == ""
