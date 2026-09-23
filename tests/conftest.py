import pytest


@pytest.fixture(autouse=True)
def isolated(tmp_path_factory, monkeypatch):
    """No test reaches the real home directory or root: HOME and the XDG
    directories point into pytest's temp dir, and sudo is a command that
    fails, so a mutation that would need root fails the test instead of
    prompting."""
    base = tmp_path_factory.mktemp("isolated")
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
    return base
