import copy
import re
import tomllib
from pathlib import Path

import pytest

from dotfiles import feature
from dotfiles.config import (
    chain,
    check,
    explain,
    init,
    resolve,
    resolve_with_sources,
)
from dotfiles.errors import ConfigError
from dotfiles.layout import Layout


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
    with Layout().defaults.open("rb") as f:
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


def test_a_missing_key_names_its_path(root):
    cfg = resolve("h", root)
    assert cfg["features"]["a"] is False
    with pytest.raises(KeyError) as e:
        cfg["features"]["nope"]
    assert str(e.value) == "features.nope: no such key in dotfiles/defaults.toml"
    assert copy.deepcopy(cfg)["features"] == {"a": False, "b": False}


def test_arrays_are_replaced(root):
    write(root, "dotfiles/defaults.toml", '[locale]\nlocales = ["en_US.UTF-8 UTF-8"]\n')
    write(root, "hosts/h.toml", '[locale]\nlocales = ["ru_RU.UTF-8 UTF-8"]\n')
    assert resolve("h", root) == {"locale": {"locales": ["ru_RU.UTF-8 UTF-8"]}}


@pytest.mark.parametrize(
    ("makepkg", "error"),
    [
        ("jobs = 4.0", "hosts/h.toml: features.packaging.makepkg.jobs: must be integer or string, got float"),
        ('jobs = "0%"', 'h: features.packaging.makepkg.jobs: must be a number of threads, or a percent of the cores like "50%", got "0%"'),
        ("jobs = -1", 'h: features.packaging.makepkg.jobs: must be a number of threads, or a percent of the cores like "50%", got -1'),
        ('packager = "Ann"', 'h: features.packaging.makepkg.packager: must be "Name <email>", got "Ann"'),
    ],
)  # fmt: skip
def test_values_the_type_cannot_check(tmp_path, makepkg, error):
    write(tmp_path, "dotfiles/defaults.toml", Layout().defaults.read_text())
    write(tmp_path, "hosts/h.toml", f"[features.packaging.makepkg]\n{makepkg}\n")
    with pytest.raises(ConfigError) as e:
        resolve("h", tmp_path, checks=feature.checks())
    assert str(e.value) == error


def test_a_key_without_default_is_there_only_when_set(tmp_path):
    write(tmp_path, "dotfiles/defaults.toml", Layout().defaults.read_text())
    write(tmp_path, "hosts/h.toml", "[features.packaging.pacman]\nmultilib = true\n")
    cfg = resolve("h", tmp_path, checks=feature.checks())
    assert cfg["features"]["packaging"] == {
        "pacman": {"contrib": False, "multilib": True},
        "makepkg": {},
    }
    write(tmp_path, "hosts/h.toml", "[features.packaging.pacman]\nmultilib = 1\n")
    with pytest.raises(ConfigError, match=r"multilib: must be boolean, got integer$"):
        resolve("h", tmp_path, checks=feature.checks())
    write(tmp_path, "hosts/h.toml", "[features.packaging.pacman]\nnope = 1\n")
    with pytest.raises(ConfigError, match=r"pacman\.nope: unknown key$"):
        resolve("h", tmp_path, checks=feature.checks())


@pytest.mark.parametrize(
    ("key", "value", "good"),
    [
        ("features.packaging.makepkg.jobs", 0, False),
        ("features.packaging.makepkg.jobs", 8, True),
        ("features.packaging.makepkg.jobs", "150%", True),
        ("features.packaging.makepkg.packager", "", False),
        ("features.packaging.makepkg.packager", "Ann Lee <ann@lee.org>", True),
        ("features.packaging.pacman.flags", ["Color", "VerbosePkgLists"], True),
        ("features.packaging.pacman.flags", ["Colour"], False),
        ("features.packaging.pacman.parallel_downloads", 0, False),
        ("features.packaging.pacman.parallel_downloads", 1, True),
    ],
)
def test_rules(key, value, good):
    from dotfiles.platforms.arch.features.packaging import Packaging

    assert bool(Packaging.rules[key.removeprefix("features.packaging.")][0](value)) is good


def test_the_schema_comes_from_the_code_not_the_source(root):
    source = root / "old-checkout"
    write(source, "dotfiles/defaults.toml", "[features]\na = false\n")  # older: no b yet
    write(source, "hosts/h.toml", "[features]\na = true\n")
    assert resolve("h", root, source=source) == {"features": {"a": True, "b": False}}


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
        (
            {"hosts/h.toml": "", "profiles/h.toml": ""},
            "ambiguous name 'h': profiles/h.toml, hosts/h.toml; give its path under hosts/",
        ),
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


def test_nested_host_by_name_or_path(root):
    write(root, "profiles/p.toml", "[features]\na = true\n")
    write(root, "hosts/vm/node/n.toml", 'extends = ["p"]\n')
    write(root, "hosts/o.toml", 'extends = ["vm/node/n"]\n[features]\nb = true\n')
    want = {"features": {"a": True, "b": False}}
    assert resolve("n", root) == resolve("n.toml", root) == want
    assert resolve("vm/node/n", root) == resolve("vm/node/n.toml", root) == want
    assert resolve("o", root) == {"features": {"a": True, "b": True}}
    assert [w for w, _ in chain("n", root)] == ["profiles/p.toml", "hosts/vm/node/n.toml"]


def test_a_name_in_two_folders_is_ambiguous(root):
    write(root, "hosts/a/n.toml", "")
    write(root, "hosts/b/n.toml", "")
    write(root, "hosts/h.toml", 'extends = ["n"]\n')
    ambiguous = "ambiguous name 'n': hosts/a/n.toml, hosts/b/n.toml; give its path under hosts/"
    with pytest.raises(ConfigError, match=f"^{re.escape(ambiguous)}$"):
        resolve("n", root)
    with pytest.raises(ConfigError, match=f"^{re.escape('hosts/h.toml: extends: ' + ambiguous)}$"):
        resolve("h", root)
    assert resolve("a/n", root) == resolve("b/n", root)
    assert list(check(root)) == ["a/n", "b/n", "h", "unknown-host"]


def test_real_profiles():
    assert [w for w, _ in chain("hyper", Layout.root)] == [
        "profiles/base.toml",
        "profiles/laptop.toml",
        "profiles/arch.toml",
        "hosts/hyper.toml",
    ]
    assert [w for w, _ in chain("echo-server", Layout.root)] == [
        "profiles/base.toml",
        "profiles/server.toml",
        "hosts/echo-server.toml",
    ]
    assert resolve("echo-server")["features"]["git"]["name"] == "Valentin Lukyanets"


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
    assert not any(check(checks=feature.checks()).values())


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
    with pytest.raises(ConfigError, match=r"^no host 'p' in "):
        init("p", root, tmp_path / "config.toml")
    assert not (tmp_path / "config.toml").exists()


def test_local_config_replaces_the_hosts_chain(root, tmp_path):
    write(root, "hosts/h.toml", "[features]\nb = true\n")
    write(tmp_path, "config.toml", "[features]\na = true\n")
    # hosts/h.toml is not read; the key the file lacks gets its default.
    got, sources = resolve_with_sources("h", root, tmp_path / "config.toml")
    assert got == {"features": {"a": True, "b": False}}
    assert sources == {"features.a": str(tmp_path / "config.toml"), "features.b": Layout.DEFAULTS}


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
