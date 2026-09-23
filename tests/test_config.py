import tomllib
from pathlib import Path

import pytest

from dotfiles.config import ROOT, ConfigError, resolve


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write(tmp_path, "defaults.toml", "[features]\na = false\nb = false\n")
    return tmp_path


def test_unknown_host_gets_defaults(root):
    assert resolve("nowhere", root) == {"features": {"a": False, "b": False}}


def test_broken_toml_names_file(root):
    write(root, "defaults.toml", "[features\n")
    with pytest.raises(ConfigError, match=r"^defaults\.toml: "):
        resolve("nowhere", root)


def test_real_defaults_parse():
    with (ROOT / "defaults.toml").open("rb") as f:
        assert resolve("unknown-host") == tomllib.load(f)


def test_host_overrides_defaults(root):
    write(root, "hosts/h.toml", "[features]\nb = true\n")
    assert resolve("h", root) == {"features": {"a": False, "b": True}}


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("[featurez]\na = true\n", "hosts/h.toml: featurez: unknown key"),
        ("[features]\nc = true\n", "hosts/h.toml: features.c: unknown key"),
        ("[features.a]\nx = 1\n", "hosts/h.toml: features.a: must be boolean, got table"),
        ("[features]\na = 1\n", "hosts/h.toml: features.a: must be boolean, got integer"),
    ],
)
def test_invalid_host_names_file_and_key(root, text, error):
    write(root, "hosts/h.toml", text)
    with pytest.raises(ConfigError) as e:
        resolve("h", root)
    assert str(e.value) == error


def test_int_is_not_bool(root):
    write(root, "defaults.toml", "[zram]\npriority = 100\n")
    write(root, "hosts/h.toml", "[zram]\npriority = true\n")
    with pytest.raises(ConfigError, match="must be integer, got boolean"):
        resolve("h", root)


def test_arrays_are_replaced(root):
    write(root, "defaults.toml", '[locale]\nlocales = ["en_US.UTF-8 UTF-8"]\n')
    write(root, "hosts/h.toml", '[locale]\nlocales = ["ru_RU.UTF-8 UTF-8"]\n')
    assert resolve("h", root) == {"locale": {"locales": ["ru_RU.UTF-8 UTF-8"]}}


def test_secrets_backend_is_checked(root):
    write(root, "defaults.toml", '[secrets]\nbackend = "none"\n')
    write(root, "hosts/h.toml", '[secrets]\nbackend = "pass"\n')
    with pytest.raises(ConfigError, match="^h: secrets.backend: must be one of none, rbw"):
        resolve("h", root)


def test_hyper_lin_matches_the_chezmoi_repo():
    """Parity with ../__dotfiles: its defaults.toml merged with its .hosts.toml table."""
    with (ROOT / "tests/fixtures/old-hosts.toml").open("rb") as f:
        old = tomllib.load(f)["hyper-lin"]
    with (ROOT / "defaults.toml").open("rb") as f:
        expected = tomllib.load(f)
    for table, values in old.items():
        expected[table].update(values)
    assert resolve("hyper-lin") == expected
