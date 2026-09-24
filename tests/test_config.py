import tomllib
from pathlib import Path

import pytest

from dotfiles.config import (
    DEFAULTS,
    ROOT,
    ConfigError,
    chain,
    check,
    explain,
    init,
    resolve,
    resolve_with_sources,
)


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write(tmp_path, "dotfiles/defaults.toml", "[features]\na = false\nb = false\n")
    return tmp_path


def test_unknown_host_gets_defaults(root):
    assert resolve("nowhere", root) == {"features": {"a": False, "b": False}}


def test_broken_toml_names_file(root):
    write(root, "dotfiles/defaults.toml", "[features\n")
    with pytest.raises(ConfigError, match=r"^dotfiles/defaults\.toml: "):
        resolve("nowhere", root)


def test_real_defaults_parse():
    with (ROOT / "dotfiles/defaults.toml").open("rb") as f:
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
    write(root, "dotfiles/defaults.toml", "[zram]\npriority = 100\n")
    write(root, "hosts/h.toml", "[zram]\npriority = true\n")
    with pytest.raises(ConfigError, match="must be integer, got boolean"):
        resolve("h", root)


def test_arrays_are_replaced(root):
    write(root, "dotfiles/defaults.toml", '[locale]\nlocales = ["en_US.UTF-8 UTF-8"]\n')
    write(root, "hosts/h.toml", '[locale]\nlocales = ["ru_RU.UTF-8 UTF-8"]\n')
    assert resolve("h", root) == {"locale": {"locales": ["ru_RU.UTF-8 UTF-8"]}}


def test_secrets_backend_is_checked(root):
    write(root, "dotfiles/defaults.toml", '[secrets]\nbackend = "none"\n')
    write(root, "hosts/h.toml", '[secrets]\nbackend = "pass"\n')
    with pytest.raises(ConfigError, match="^h: secrets.backend: must be one of none, rbw"):
        resolve("h", root)


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
    assert echo["features"]["sshd"]["enabled"] and echo["features"]["zsh"]["enabled"]
    assert not echo["features"]["niri"]["enabled"]


def test_check_reports_every_broken_host(root):
    write(root, "hosts/good.toml", "[features]\na = true\n")
    write(root, "hosts/bad1.toml", "[features]\nc = true\n")
    write(root, "hosts/bad2.toml", 'extends = ["nope"]\n')
    assert check(root) == {
        "bad1": "hosts/bad1.toml: features.c: unknown key",
        "bad2": "hosts/bad2.toml: extends: no profile or host 'nope'",
        "good": None,
        "unknown-host": None,
    }


def test_check_real_data():
    assert not any(check().values())


def test_explain_names_the_file_of_each_value(root):
    write(
        root,
        "dotfiles/defaults.toml",
        '[features]\na = false\nb = false\nc = false\n[locale]\nlocales = ["en", "ru"]\n',
    )
    write(root, "profiles/p.toml", "[features]\nb = true\n")
    write(root, "hosts/h.toml", 'extends = ["p"]\n[features]\nc = true\n')
    text = explain("h", root)
    assert text == (
        "features.a = false  # dotfiles/defaults.toml\n"
        "features.b = true  # profiles/p.toml\n"
        "features.c = true  # hosts/h.toml\n"
        'locale.locales = ["en", "ru"]  # dotfiles/defaults.toml\n'
    )
    assert tomllib.loads(text) == resolve("h", root)


def test_tests_run_isolated(isolated):
    import os

    assert Path.home() == isolated / "home"
    assert os.environ["XDG_RUNTIME_DIR"] == str(isolated / "run")
    assert os.environ["SUDO_CMD"] == "false"


def test_init_writes_the_resolved_host_then_nothing(root, tmp_path):
    write(root, "profiles/p.toml", "[features]\na = true\n")
    write(root, "hosts/h.toml", 'extends = ["p"]\n')
    local = tmp_path / "local/dotfiles/config.toml"
    assert init("h", root, local) == f"-> {local} (missing)"
    assert tomllib.loads(local.read_text()) == resolve("h", root)
    assert local.read_text().startswith("# This machine's config: hosts/h.toml")
    assert init("h", root, local) is None
    write(root, "hosts/h.toml", 'extends = ["p"]\n[features]\nb = true\n')
    assert init("h", root, local) == f"-> {local} (content differs)"
    assert resolve("x", root, local) == {"features": {"a": True, "b": True}}


def test_init_needs_a_host_file(root, tmp_path):
    write(root, "profiles/p.toml", "")
    with pytest.raises(ConfigError, match=r"^no hosts/p\.toml in "):
        init("p", root, tmp_path / "config.toml")
    assert not (tmp_path / "config.toml").exists()


def test_local_config_replaces_the_hosts_chain(root, tmp_path):
    write(root, "hosts/h.toml", "[features]\nb = true\n")
    write(tmp_path, "config.toml", "[features]\na = true\n")
    # hosts/h.toml is not read; the key the file lacks gets its default.
    got, sources = resolve_with_sources("h", root, tmp_path / "config.toml")
    assert got == {"features": {"a": True, "b": False}}
    assert sources == {"features.a": str(tmp_path / "config.toml"), "features.b": DEFAULTS}


@pytest.mark.parametrize(
    "text, error",
    [
        ("[features]\nc = true\n", "features.c: unknown key"),
        ('extends = ["p"]\n', "extends: unknown key"),
        ("[features]\na = 1\n", "features.a: must be boolean, got integer"),
    ],
)
def test_local_config_is_validated(root, tmp_path, text, error):
    write(tmp_path, "config.toml", text)
    with pytest.raises(ConfigError, match=f"^{tmp_path}/config.toml: {error}$"):
        resolve("h", root, tmp_path / "config.toml")


def test_missing_local_config_says_how_to_make_one(root):
    local = Path.home() / ".config/dotfiles/config.toml"
    with pytest.raises(ConfigError) as e:
        resolve("h", root, local)
    assert str(e.value) == (
        "no ~/.config/dotfiles/config.toml — run dotfiles init <host>, or pass --source <checkout>"
    )
