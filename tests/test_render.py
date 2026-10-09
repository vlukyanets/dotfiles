import re
import shutil
import tomllib
from pathlib import Path

import pytest

from dotfiles import feature
from dotfiles.apply import check
from dotfiles.errors import ConfigError
from dotfiles.layout import Layout
from dotfiles.render import template


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_check_names_a_value_the_type_allows(tmp_path):
    for sub in ("hosts", "profiles"):
        shutil.copytree(Layout.root / sub, tmp_path / sub)
    (tmp_path / "dotfiles").mkdir()
    shutil.copy(Layout().defaults, tmp_path / "dotfiles")
    (tmp_path / "hosts/solo.toml").write_text('[features.packaging.makepkg]\njobs = "fast"\n')
    assert check(source=tmp_path)["solo"] == (
        "solo: features.packaging.makepkg.jobs: must be a number of threads, "
        'or a percent of the cores like "50%", got "fast"'
    )


def test_system_templates(tmp_path):
    root = tmp_path
    write(root, "system/etc/x.conf.j2", "a = {{ a }}\n{% if b %}\nb\n{% endif %}\n")
    assert template("/etc/x.conf", root, a=1, b=False) == "a = 1\n"
    write(root, "system/etc/y.conf.j2", "\n{{ fail('no a') }}")
    with pytest.raises(ConfigError, match="^system/etc/y.conf.j2:2: no a$"):
        template("/etc/y.conf", root)
    write(root, "system/etc/z.conf.j2", "{{ nope }}")
    with pytest.raises(ConfigError, match="^system/etc/z.conf.j2:1: 'nope' is undefined$"):
        template("/etc/z.conf", root)


def test_home_templates(tmp_path):
    write(tmp_path, "home/.config/x.j2", "a = {{ a }}\n")
    assert template("~/.config/x", tmp_path, a=1) == "a = 1\n"
    write(tmp_path, "home/.y.j2", "{{ nope }}")
    with pytest.raises(ConfigError, match="^home/.y.j2:1: 'nope' is undefined$"):
        template("~/.y", tmp_path)


def test_merge_over():
    from dotfiles.config import merge_over

    assert merge_over({"a": {"x": 1}, "b": 2}, {"a": {"x": 0, "y": 0}, "c": 3}) == {
        "a": {"x": 1, "y": 0},
        "c": 3,
        "b": 2,
    }
    assert merge_over({"a": 1}, {"a": {"x": 0}}) == {"a": 1}


def test_templates_name_keys_the_schema_has():
    schema = tomllib.loads(Layout().defaults.read_text())
    types = feature.checks().types  # keys with no default: packaging.pacman.multilib
    for path in sorted([*Layout().system.rglob("*.j2"), *Layout().home.rglob("*.j2")]):
        for key in re.findall(r"\bfeatures\.[a-z_.]*[a-z_]", path.read_text()):
            if key in types:
                continue
            found = schema
            for part in key.split("."):
                assert isinstance(found, dict) and part in found, f"{path}: {key}: no such key"
                found = found[part]
