import os
import shutil
import subprocess
from pathlib import Path

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


@pytest.fixture(scope="session", autouse=True)
def isolated_session(tmp_path_factory):
    with pytest.MonkeyPatch.context() as mp:
        isolate(mp, tmp_path_factory.mktemp("session"))
        yield


@pytest.fixture(autouse=True)
def isolated(tmp_path_factory, monkeypatch):
    base = tmp_path_factory.mktemp("isolated")
    isolate(monkeypatch, base)
    with engine.Machine(sysroot=base / "sysroot").active():
        yield base


class Fake:
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

    def root(self, sudo, argv, **kwargs):
        """Shell.root: the command with its sudo prefix, like any other."""
        return self([*sudo, *argv], **kwargs)

    def install(self, monkeypatch):
        """Every command of the current machine's shell through this fake."""
        monkeypatch.setattr(engine.current().shell, "execute", self)
        monkeypatch.setattr(engine.current().shell, "root", self.root)
        return self


@pytest.fixture
def fake(monkeypatch) -> Fake:
    return Fake().install(monkeypatch)


class AsRoot(Fake):
    def __call__(self, argv, check=False, **kwargs):
        if argv[0] == "install":
            dst = Path(argv[-1])
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(argv[-2], dst)
            dst.chmod(int(argv[argv.index("-m") + 1], 8))
        if argv[:2] == ["git", "clone"] and not self.answers.get(tuple(argv), (0,))[0]:
            Path(argv[-1]).mkdir(parents=True)
        if argv[:2] == ["ln", "-sfn"]:
            Path(argv[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(argv[-1]).unlink(missing_ok=True)
            os.symlink(argv[-2], argv[-1])
        return super().__call__(argv, check, **kwargs)


@pytest.fixture
def machine(monkeypatch) -> AsRoot:
    """Every command faked, root's files written under SYSROOT, no sudo prefix."""
    fake = AsRoot().install(monkeypatch)
    monkeypatch.setattr(engine, "_owner", lambda path: "root:root")
    monkeypatch.setenv("SUDO_CMD", "")
    return fake
