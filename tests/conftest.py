import subprocess

import pytest

from dotfiles import engine


def isolate(monkeypatch, base):
    """HOME and the XDG directories inside BASE, and a sudo that fails."""
    home = base / "home"
    for var, path in {
        "HOME": home,
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local/share",
        "XDG_STATE_HOME": home / ".local/state",
        "XDG_CACHE_HOME": home / ".cache",
        "XDG_RUNTIME_DIR": base / "run",
    }.items():
        path.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(var, str(path))
    monkeypatch.setenv("SUDO_CMD", "false")
    # dotfiles apply sets these for a host with snapper; setenv first so the
    # monkeypatch removes them again even when they were not set before.
    for var in ("SNAP_PAC_SKIP", "DOTFILES_SNAPPER_STATE"):
        monkeypatch.setenv(var, "")
        monkeypatch.delenv(var)


@pytest.fixture(scope="session", autouse=True)
def isolated_session(tmp_path_factory):
    """The same for session- and module-scoped fixtures, which are set up
    before any function-scoped one."""
    with pytest.MonkeyPatch.context() as mp:
        isolate(mp, tmp_path_factory.mktemp("session"))
        yield


@pytest.fixture(autouse=True)
def isolated(tmp_path_factory, monkeypatch):
    """No test reaches the real home directory or root: every test gets its
    own HOME and XDG directories in pytest's temp dir, the engine's helpers
    work under a temp SYSROOT, and sudo is a command that fails, so a
    mutation that would need root fails the test instead of prompting."""
    base = tmp_path_factory.mktemp("isolated")
    isolate(monkeypatch, base)
    monkeypatch.setattr(engine, "DRY_RUN", False)
    monkeypatch.setattr(engine, "SYSROOT", base / "sysroot")
    monkeypatch.setattr(engine, "notices", [])
    return base


class Fake:
    """Stands in for engine._run: answers from ANSWERS (argv tuple -> (rc,
    stdout)), 0 and "" otherwise, and records every argv in CALLS. With
    PROGRAMS, only those are faked; anything else really runs."""

    def __init__(self, programs=None):
        self.answers: dict[tuple, tuple[int, str]] = {}
        self.calls: list[list[str]] = []
        self.programs = programs

    def __call__(self, argv, check=False, **kwargs):
        if self.programs is not None and argv[0] not in self.programs:
            return subprocess.run(argv, check=check, text=True, **kwargs)
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
