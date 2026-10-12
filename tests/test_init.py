"""Tests for dotfiles init and for finding the repository, on a fake filesystem."""

import subprocess
from pathlib import Path

import pytest

from dotfiles import init as init_module
from dotfiles.add import Error
from dotfiles.init import URL, clone_dir, find_repo, init


def test_finds_the_checkout_its_code_runs_from():
    # The real filesystem: this test runs from a clone.
    assert find_repo() == Path(init_module.__file__).resolve().parents[1]


@pytest.fixture
def no_checkout(fs, monkeypatch):
    """A machine where the code is installed, not cloned."""
    monkeypatch.delenv("DOTFILES_REPO", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", "/home/alice/.local/share")


def test_finds_the_clone_in_its_default_place(no_checkout, fs):
    fs.create_file("/home/alice/.local/share/dotfiles/secret_leaks.toml")
    assert str(find_repo()) == "/home/alice/.local/share/dotfiles"


def test_finds_the_clone_named_by_dotfiles_repo(no_checkout, fs, monkeypatch):
    fs.create_file("/srv/dots/secret_leaks.toml")
    monkeypatch.setenv("DOTFILES_REPO", "/srv/dots")
    assert str(find_repo()) == "/srv/dots"


def test_without_a_clone_says_to_init(no_checkout):
    with pytest.raises(Error, match="no dotfiles repository in /home/alice/.local/share/dotfiles; run dotfiles init"):
        find_repo()


@pytest.fixture
def git(monkeypatch):
    """git, here: notes each call."""
    calls = []
    monkeypatch.setattr(init_module.subprocess, "run", lambda args, **kwargs: calls.append(args))
    return calls


def test_init_clones_into_the_default_place(no_checkout, git, capsys):
    init()

    target = str(clone_dir())
    assert git == [["git", "clone", "--quiet", URL, target]]
    assert capsys.readouterr().out == f"cloned {URL} into {target}\n"


def test_init_dry_run_clones_nothing(no_checkout, git, capsys):
    init("https://example.org/other", dry_run=True)

    assert git == []
    assert capsys.readouterr().out.startswith("cloned https://example.org/other into ")


def test_init_into_an_empty_directory(no_checkout, fs, git):
    fs.create_dir(str(clone_dir()))
    init()
    assert len(git) == 1


def test_init_refuses_a_directory_in_use(no_checkout, fs, git):
    fs.create_file(str(clone_dir() / "x"))
    with pytest.raises(Error, match="already there, and not empty"):
        init()
    assert git == []


def test_init_without_git(no_checkout, monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError("git")
    monkeypatch.setattr(init_module.subprocess, "run", missing)
    with pytest.raises(Error, match="git is needed"):
        init()


def test_init_reports_what_git_says(no_checkout, monkeypatch):
    def fails(*args, **kwargs):
        raise subprocess.CalledProcessError(128, args, stderr="fatal: repository not found\n")
    monkeypatch.setattr(init_module.subprocess, "run", fails)
    with pytest.raises(Error, match=f"git clone {URL}: fatal: repository not found$"):
        init()
