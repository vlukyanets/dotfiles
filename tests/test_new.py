"""Tests for dotfiles new, on a fake filesystem."""

from pathlib import Path

import pytest

from dotfiles.add import Error
from dotfiles.init import MARK
from dotfiles.new import new

REPO = Path("/repo")
HOST = REPO / "hosts/hyper"


def test_makes_the_host_with_an_empty_meta(fs, capsys):
    new(REPO, "hyper")
    assert (HOST / ".meta").read_text() == ""
    assert capsys.readouterr().out == "added hosts/hyper/.meta\n"


def test_leaves_a_host_that_exists(fs, capsys):
    fs.create_file(HOST / "etc/hosts")
    new(REPO, "hyper")
    assert not (HOST / ".meta").exists()
    assert capsys.readouterr().out == "unchanged hosts/hyper/\n"


def test_dry_run_makes_nothing(fs, capsys):
    new(REPO, "hyper", dry_run=True)
    assert not HOST.exists()
    assert capsys.readouterr().out == "added hosts/hyper/.meta\n"


def test_rejects_a_bad_host_name(fs):
    with pytest.raises(Error, match="bad host name: ../x"):
        new(REPO, "../x")
    assert not (REPO / "hosts").exists()


def test_command_takes_the_hostname(fs, monkeypatch, capsys):
    from dotfiles.cli import main

    monkeypatch.setenv("DOTFILES_REPO", str(REPO))  # for the command, see dotfiles.init
    monkeypatch.setattr("socket.gethostname", lambda: "hyper")
    fs.create_file(REPO / MARK)
    assert main(["new"]) == 0
    assert main(["new", "--host", "other"]) == 0
    assert (HOST / ".meta").is_file()
    assert (REPO / "hosts/other/.meta").is_file()
