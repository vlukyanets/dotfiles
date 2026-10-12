"""Tests for templates and their values file, on a fake filesystem."""

import io
import os
import tomllib
from pathlib import Path

import pytest

from dotfiles import template
from dotfiles.add import Error
from dotfiles.template import (
    fill,
    names,
    read_values,
    save_value,
    toml_string,
    values_for,
)

CONFIG = Path("/home/alice/.config")
VALUES = CONFIG / "dotfiles/hyper.toml"
NODE = Path("/repo/nodes/hyper")


class Terminal(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture(autouse=True)
def config(fs, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(CONFIG))
    fs.create_dir(NODE)


def asked(monkeypatch, answers):
    """Answers each value asked for in turn, noting the prompts."""
    prompts = []
    monkeypatch.setattr(template.sys, "stdin", Terminal())

    def ask(prompt):
        prompts.append(prompt)
        return answers.pop(0)
    monkeypatch.setattr(template.getpass, "getpass", ask)
    return prompts


def test_names_and_fill():
    text = "a={{ a }} b={{b}} again={{  a  }} not={{ B }} {x}\n"
    assert names(text) == ["a", "b"]
    assert fill(text, {"a": "1", "b": "\\2"}) == "a=1 b=\\2 again=1 not={{ B }} {x}\n"


@pytest.mark.parametrize("value", ['plain', 'q"uote', "back\\slash", "tab\tnew\nline", "\x00\x7f", "ключ ✓ 😀"])
def test_toml_string_reads_back(value):
    assert tomllib.loads(f"v = {toml_string(value)}")["v"] == value


def test_values_path_follows_xdg_config_home(monkeypatch):
    assert str(template.values_path("hyper")) == str(VALUES)
    monkeypatch.delenv("XDG_CONFIG_HOME")
    assert str(template.values_path("hyper")) == str(Path.home() / ".config/dotfiles/hyper.toml")


def test_saved_values_are_closed_to_others():
    save_value(VALUES, "a", "1")
    save_value(VALUES, "b", "2")

    assert read_values(VALUES) == {"a": "1", "b": "2"}
    assert os.stat(VALUES).st_mode & 0o777 == 0o600
    assert os.stat(VALUES.parent).st_mode & 0o777 == 0o700


def test_a_value_that_is_not_a_string():
    VALUES.parent.mkdir(parents=True)
    VALUES.write_text("port = 22\n")
    with pytest.raises(Error, match="port is not a string"):
        read_values(VALUES)


def test_a_broken_values_file_names_no_value():
    VALUES.parent.mkdir(parents=True)
    VALUES.write_text('a = "secret\n')
    with pytest.raises(Error) as error:
        read_values(VALUES)
    assert "secret" not in str(error.value)


def test_asks_for_each_missing_value_once_and_saves_it(monkeypatch):
    save_value(VALUES, "known", "k")
    (NODE / "etc").mkdir(parents=True)
    (NODE / "etc/a.tmpl").write_text("{{ known }} {{ psk }}\n")
    (NODE / "etc/b.tmpl").write_text("{{ psk }} {{ token }}\n")
    prompts = asked(monkeypatch, ["p", "t"])

    assert values_for(NODE, ask=True) == {"known": "k", "psk": "p", "token": "t"}
    assert prompts == ["value for psk: ", "value for token: "]
    assert read_values(VALUES) == {"known": "k", "psk": "p", "token": "t"}


def test_without_ask_a_missing_value_stays_missing(monkeypatch):
    (NODE / "a.tmpl").write_text("{{ psk }}\n")
    prompts = asked(monkeypatch, [])

    assert values_for(NODE, ask=False) == {}
    assert prompts == []
    assert not VALUES.exists()


def test_does_not_ask_without_a_terminal(monkeypatch):
    (NODE / "a.tmpl").write_text("{{ psk }}\n")
    monkeypatch.setattr(template.sys, "stdin", io.StringIO())

    with pytest.raises(Error, match=f"no value for psk in {VALUES}"):
        values_for(NODE, ask=True)


def test_a_template_must_be_utf8():
    (NODE / "a.tmpl").write_bytes(b"\xff")
    with pytest.raises(Error, match="a template must be UTF-8 text"):
        values_for(NODE, ask=False)
