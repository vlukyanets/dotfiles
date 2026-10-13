"""Tests for dotfiles check, on a fake filesystem with no machine behind it."""

from pathlib import Path

import pytest

from dotfiles import cli
from dotfiles import install as install_module
from dotfiles.check import check

REPO = Path("/repo")
NOT_ONE = "not `<mode> <owner>:<group> <path>`"


class NoSudo:
    def __getattr__(self, op):
        raise AssertionError(f"check used sudo: {op}")


@pytest.fixture(autouse=True)
def repo(fs, monkeypatch):
    """A repository and no machine: no /etc, no sudo."""
    monkeypatch.setattr(install_module, "sudo", NoSudo())
    fs.create_file(REPO / "secret_leaks.toml")


def node(name, *meta):
    (REPO / "nodes" / name / "etc").mkdir(parents=True)
    (REPO / "nodes" / name / "etc/x").write_text("x\n")
    if meta:
        (REPO / "nodes" / name / ".meta").write_text("".join(line + "\n" for line in meta))


def test_every_node_fine(capsys):
    node("b")
    node("a")

    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "a: ok\nb: ok\n"


def test_no_nodes(capsys):
    assert check(REPO, []) == 0
    (REPO / "nodes").mkdir()
    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "no nodes to check\n" * 2


def test_a_broken_node_shows_all_its_problems_and_the_next_is_checked(capsys):
    node("a", "bad", "0600 root:root etc/nope")
    node("b")

    assert check(REPO, []) == 1
    assert capsys.readouterr().out == (
        "a:\n"
        f"  {REPO}/nodes/a/.meta:1: {NOT_ONE}\n"
        f"  {REPO}/nodes/a/.meta: the node has no etc/nope\n"
        "b: ok\n")


def test_checks_only_the_nodes_named(capsys):
    node("a", "bad")
    node("b")

    assert check(REPO, ["b"]) == 0
    assert capsys.readouterr().out == "b: ok\n"


def test_a_missing_node(capsys):
    node("a")

    assert check(REPO, ["nope"]) == 1
    assert capsys.readouterr().out == "nope: no such node\n"


def test_a_bad_node_name(capsys):
    node("Laptop")

    assert check(REPO, []) == 1
    assert check(REPO, ["../nodes/Laptop"]) == 1
    assert capsys.readouterr().out == "Laptop: bad node name\n../nodes/Laptop: bad node name\n"


def test_a_file_in_nodes_is_not_a_node(capsys):
    node("a")
    (REPO / "nodes/README").write_text("x\n")

    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "a: ok\n"


def test_the_command_runs_as_root(monkeypatch, capsys):
    node("a")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)

    assert cli.main(["check"]) == 0
    assert cli.main(["check", "nope"]) == 1
    assert capsys.readouterr().out == "a: ok\nnope: no such node\n"
