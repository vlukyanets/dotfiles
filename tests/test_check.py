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


def host(name, *meta):
    (REPO / "hosts" / name / "etc").mkdir(parents=True)
    (REPO / "hosts" / name / "etc/x").write_text("x\n")
    if meta:
        (REPO / "hosts" / name / ".meta").write_text("".join(line + "\n" for line in meta))


def test_every_host_fine(capsys):
    host("b")
    host("a")

    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "a: ok\nb: ok\n"


def test_no_hosts(capsys):
    assert check(REPO, []) == 0
    (REPO / "hosts").mkdir()
    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "no hosts to check\n" * 2


def test_a_broken_host_shows_all_its_problems_and_the_next_is_checked(capsys):
    host("a", "bad", "0600 root:root etc/nope")
    host("b")

    assert check(REPO, []) == 1
    assert capsys.readouterr().out == (
        "a:\n"
        f"  {REPO}/hosts/a/.meta:1: {NOT_ONE}\n"
        f"  {REPO}/hosts/a/.meta: the host has no etc/nope\n"
        "b: ok\n")


def test_checks_only_the_hosts_named(capsys):
    host("a", "bad")
    host("b")

    assert check(REPO, ["b"]) == 0
    assert capsys.readouterr().out == "b: ok\n"


def test_a_missing_host(capsys):
    host("a")

    assert check(REPO, ["nope"]) == 1
    assert capsys.readouterr().out == "nope: no such host\n"


def test_a_bad_host_name(capsys):
    host("laptop_1")

    assert check(REPO, []) == 1
    assert check(REPO, ["../hosts/laptop_1", "hyper.", "a..b"]) == 1
    assert capsys.readouterr().out == (
        "laptop_1: bad host name\n../hosts/laptop_1: bad host name\n"
        "hyper.: bad host name\na..b: bad host name\n")


def test_a_hostname_with_dots_and_capitals(capsys):
    host("Hyper.local")

    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "Hyper.local: ok\n"


def test_a_file_in_hosts_is_not_a_host(capsys):
    host("a")
    (REPO / "hosts/README").write_text("x\n")

    assert check(REPO, []) == 0
    assert capsys.readouterr().out == "a: ok\n"


def test_the_command_runs_as_root(monkeypatch, capsys):
    host("a")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))
    monkeypatch.setattr(cli.os, "geteuid", lambda: 0)

    assert cli.main(["check"]) == 0
    assert cli.main(["check", "nope"]) == 1
    assert capsys.readouterr().out == "a: ok\nnope: no such host\n"
