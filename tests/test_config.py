import tomllib
from pathlib import Path

import pytest

from dotfiles.config import ROOT, ConfigError, chain, resolve


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


def test_host_extends_profile_and_overrides_it(root):
    write(root, "profiles/p.toml", "[features]\na = true\nb = true\n")
    write(root, "hosts/h.toml", 'extends = ["p"]\n[features]\nb = false\n')
    assert resolve("h", root) == {"features": {"a": True, "b": False}}


def test_parents_merge_left_to_right(root):
    write(root, "profiles/p.toml", "[features]\na = true\n")
    write(root, "profiles/q.toml", "[features]\na = false\nb = true\n")
    write(root, "hosts/h.toml", 'extends = ["p", "q"]\n')
    assert resolve("h", root) == {"features": {"a": False, "b": True}}


def test_shared_ancestor_is_merged_once(root):
    write(root, "profiles/base.toml", "[features]\na = false\nb = false\n")
    write(root, "profiles/p.toml", 'extends = ["base"]\n[features]\na = true\n')
    write(root, "profiles/q.toml", 'extends = ["base"]\n[features]\nb = true\n')
    write(root, "hosts/h.toml", 'extends = ["p", "q"]\n')
    # q re-merging base would reset a.
    assert resolve("h", root) == {"features": {"a": True, "b": True}}


def test_host_extends_host(root):
    write(root, "hosts/one.toml", "[features]\na = true\n")
    write(root, "hosts/two.toml", 'extends = ["one"]\n')
    assert resolve("two", root) == {"features": {"a": True, "b": False}}


def test_hostname_does_not_pick_up_a_profile(root):
    write(root, "profiles/server.toml", "[features]\na = true\n")
    assert resolve("server", root) == {"features": {"a": False, "b": False}}


@pytest.mark.parametrize(
    ("files", "error"),
    [
        (
            {"hosts/h.toml": 'extends = ["p"]\n', "profiles/p.toml": 'extends = ["h"]\n'},
            "extends: cycle h → p → h",
        ),
        ({"hosts/h.toml": 'extends = ["h"]\n'}, "extends: cycle h → h"),
        (
            {"hosts/h.toml": 'extends = ["nope"]\n'},
            "hosts/h.toml: extends: no profile or host 'nope'",
        ),
        ({"hosts/h.toml": 'extends = "p"\n'}, "hosts/h.toml: extends: must be an array of strings"),
        ({"hosts/h.toml": "extends = [1]\n"}, "hosts/h.toml: extends: must be an array of strings"),
        ({"hosts/h.toml": "", "profiles/h.toml": ""}, "hosts/h.toml: 'h' is also profiles/h.toml"),
        (
            {"hosts/h.toml": 'extends = ["p"]\n', "profiles/p.toml": "[features]\nc = 1\n"},
            "profiles/p.toml: features.c: unknown key",
        ),
        (
            {"hosts/h.toml": '[features]\nextends = ["p"]\n'},
            "hosts/h.toml: features.extends: unknown key",
        ),
    ],
)
def test_bad_inheritance(root, files, error):
    for rel, text in files.items():
        write(root, rel, text)
    with pytest.raises(ConfigError) as e:
        resolve("h", root)
    assert str(e.value) == error


def test_real_profiles():
    assert [w for w, _ in chain("hyper-lin", ROOT)] == [
        "profiles/base.toml",
        "profiles/laptop.toml",
        "hosts/hyper-lin.toml",
    ]
    assert [w for w, _ in chain("echo-server", ROOT)] == [
        "profiles/base.toml",
        "profiles/server.toml",
        "hosts/echo-server.toml",
    ]
    echo = resolve("echo-server")
    assert echo["features"]["sshd"] and echo["features"]["zsh"]
    assert not echo["features"]["niri"]
