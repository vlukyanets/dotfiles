"""Tests for dotfiles restore, on the fake machine of test_install."""

import os
from datetime import datetime

import pytest
from test_install import (  # noqa: F401
    ALICE,
    REPO,
    ROOT,
    STAMP,
    as_root,
    machine,
    make,
    node_file,
    node_link,
    read,
    state,
)

from dotfiles import install as install_module
from dotfiles.add import Error
from dotfiles.install import install
from dotfiles.restore import restore

LATER = "20261012-080000"


def installed(monkeypatch, capsys, when=None):
    """Runs install, then moves the clock to LATER, or to when."""
    install(REPO, "hyper")
    capsys.readouterr()
    monkeypatch.setattr(install_module, "now", lambda: when or datetime(2026, 10, 12, 8, 0, 0))


def test_puts_back_what_install_replaced(monkeypatch, capsys):
    make("/etc/x", 0o600, ROOT, b"old\n")
    make("/home/alice/y", 0o755, ALICE, b"old y\n")
    node_file("etc/x")
    node_file("home/alice/y")
    installed(monkeypatch, capsys)

    restore(REPO, "hyper")

    assert read("/etc/x") == b"old\n"
    assert state("/etc/x") == (0o600, ROOT, ROOT)
    assert read("/home/alice/y") == b"old y\n"
    assert state("/home/alice/y") == (0o755, ALICE, ALICE)
    later = f"/repo/.backups/hyper/{LATER}"
    assert capsys.readouterr().out == (
        f"updated /etc/x (backup {later}/etc/x)\n"
        f"updated /home/alice/y (backup {later}/home/alice/y)\n")
    assert read(f"{later}/etc/x") == b"new\n"


def test_puts_back_a_replaced_symlink(monkeypatch, capsys):
    as_root(os.symlink)("/usr/share/zoneinfo/A", "/etc/localtime")
    node_link("etc/localtime", "/usr/share/zoneinfo/B")
    installed(monkeypatch, capsys)

    restore(REPO, "hyper", None, ["/etc/localtime"])

    later = f"/repo/.backups/hyper/{LATER}"
    assert os.readlink("/etc/localtime") == "/usr/share/zoneinfo/A"
    assert capsys.readouterr().out == (
        f"updated /etc/localtime -> /usr/share/zoneinfo/A (backup {later}/etc/localtime)\n")


def test_puts_back_only_the_paths_given(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"old\n")
    make("/etc/y", 0o644, ROOT, b"old\n")
    node_file("etc/x")
    node_file("etc/y")
    installed(monkeypatch, capsys)

    restore(REPO, "hyper", paths=["/etc/y"])

    assert read("/etc/x") == b"new\n"
    assert read("/etc/y") == b"old\n"


def test_puts_back_the_run_named(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"first\n")
    node_file("etc/x", b"second\n")
    installed(monkeypatch, capsys)
    node_file("etc/x", b"third\n")
    installed(monkeypatch, capsys, when=datetime(2026, 10, 13, 8, 0, 0))

    restore(REPO, "hyper", STAMP)

    assert read("/etc/x") == b"first\n"


def test_puts_back_the_last_run_by_default(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"first\n")
    node_file("etc/x", b"second\n")
    installed(monkeypatch, capsys)
    node_file("etc/x", b"third\n")
    installed(monkeypatch, capsys, when=datetime(2026, 10, 13, 8, 0, 0))

    restore(REPO, "hyper")

    assert read("/etc/x") == b"second\n"


def test_runs_the_hooks_of_the_node(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"old\n")
    node_file("etc/x")
    (REPO / "nodes/hyper/.hooks").write_text("etc/x sudo systemctl reload x\n")
    monkeypatch.setattr(install_module, "run_hook", lambda command: None)
    installed(monkeypatch, capsys)
    ran = []
    monkeypatch.setattr(install_module, "run_hook", ran.append)

    restore(REPO, "hyper")

    assert ran == ["sudo systemctl reload x"]


def test_dry_run_changes_nothing(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"old\n")
    node_file("etc/x")
    installed(monkeypatch, capsys)

    restore(REPO, "hyper", dry_run=True)

    assert read("/etc/x") == b"new\n"
    assert os.listdir(REPO / ".backups/hyper") == [STAMP]
    assert capsys.readouterr().out.startswith("updated /etc/x")


@pytest.mark.parametrize(
    "args, message",
    [
        (("laptop",), "no backups of laptop"),
        (("hyper", "20990101-000000"), "no such backup: hyper/20990101-000000"),
        (("hyper", "../x"), "no such backup: hyper/../x"),
        (("hyper", None, ["/etc/nope"]), f"not in backup hyper/{STAMP}: /etc/nope"),
        (("hyper", None, ["etc/x"]), f"not in backup hyper/{STAMP}: etc/x"),
    ],
)
def test_refuses(monkeypatch, capsys, args, message):
    make("/etc/x", 0o644, ROOT, b"old\n")
    node_file("etc/x")
    installed(monkeypatch, capsys)

    with pytest.raises(Error, match=message):
        restore(REPO, *args)


def test_refuses_a_backup_made_this_second(monkeypatch, capsys):
    make("/etc/x", 0o644, ROOT, b"old\n")
    node_file("etc/x")
    installed(monkeypatch, capsys, when=datetime(2026, 10, 11, 21, 30, 0))

    with pytest.raises(Error, match="made this second"):
        restore(REPO, "hyper")


def test_command_takes_one_run_at_most(capsys):
    from dotfiles.cli import main

    assert main(["restore", "hyper", "20261011-213000", "20261012-080000"]) == 1
    assert "one run at most" in capsys.readouterr().err
