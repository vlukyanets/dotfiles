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
