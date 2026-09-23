import pytest


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
    """The same for session- and module-scoped fixtures, which are set up
    before any function-scoped one."""
    with pytest.MonkeyPatch.context() as mp:
        isolate(mp, tmp_path_factory.mktemp("session"))
        yield


@pytest.fixture(autouse=True)
def isolated(tmp_path_factory, monkeypatch):
    """No test reaches the real home directory or root: every test gets its
    own HOME and XDG directories in pytest's temp dir, and sudo is a command
    that fails, so a mutation that would need root fails the test instead of
    prompting."""
    base = tmp_path_factory.mktemp("isolated")
    isolate(monkeypatch, base)
    return base
