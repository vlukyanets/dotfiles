"""Tests for dotfiles forget, on a fake filesystem."""

import os
from pathlib import Path

import pytest

from dotfiles.add import Error
from dotfiles.forget import forget

REPO = Path("/repo")
NODE = REPO / "nodes/hyper"


def node_files():
    return sorted(str(p.relative_to(NODE)) for p in NODE.rglob("*"))


@pytest.fixture(autouse=True)
def node_dir(fs):
    fs.create_file(NODE / "etc/ssh/sshd_config.d/10-local.conf")
    fs.create_file(NODE / "etc/ssh/ssh_host_ed25519_key")
    fs.create_file(NODE / "home/alice/.ssh/config.tmpl")
    fs.create_file(NODE / ".meta", contents=(
        "0600 root:root etc/ssh/ssh_host_ed25519_key\n"
        "0700 alice:alice home/alice/.ssh/\n"
        "0600 alice:alice home/alice/.ssh/config.tmpl\n"
    ))


def test_removes_the_file_and_its_line(capsys):
    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key"])

    assert not (NODE / "etc/ssh/ssh_host_ed25519_key").exists()
    assert (NODE / "etc/ssh/sshd_config.d/10-local.conf").exists()
    assert (NODE / ".meta").read_text() == (
        "0700 alice:alice home/alice/.ssh/\n"
        "0600 alice:alice home/alice/.ssh/config.tmpl\n")
    assert capsys.readouterr().out == (
        "removed nodes/hyper/etc/ssh/ssh_host_ed25519_key\n"
        "meta: removed etc/ssh/ssh_host_ed25519_key\n")


def test_removes_a_template_and_the_directories_left_empty(capsys):
    forget(REPO, "hyper", ["/home/alice/.ssh/config"])

    assert not (NODE / "home").exists()
    assert (NODE / ".meta").read_text() == "0600 root:root etc/ssh/ssh_host_ed25519_key\n"
    assert capsys.readouterr().out == (
        "removed nodes/hyper/home/alice/.ssh/config.tmpl\n"
        "meta: removed home/alice/.ssh/config.tmpl\n"
        "removed nodes/hyper/home/alice/.ssh/\n"
        "meta: removed home/alice/.ssh/\n"
        "removed nodes/hyper/home/alice/\n"
        "removed nodes/hyper/home/\n")


def test_removes_the_meta_file_once_it_is_empty():
    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/home/alice/.ssh/config"])

    assert node_files() == ["etc", "etc/ssh", "etc/ssh/sshd_config.d",
                            "etc/ssh/sshd_config.d/10-local.conf"]


def test_dry_run_changes_nothing(capsys):
    before = node_files(), (NODE / ".meta").read_text()

    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/etc/ssh/sshd_config.d/10-local.conf",
                           "/etc/ssh/sshd_config.d/10-local.conf"], dry_run=True)

    assert (node_files(), (NODE / ".meta").read_text()) == before
    assert capsys.readouterr().out == (
        "removed nodes/hyper/etc/ssh/ssh_host_ed25519_key\n"
        "meta: removed etc/ssh/ssh_host_ed25519_key\n"
        "removed nodes/hyper/etc/ssh/sshd_config.d/10-local.conf\n"
        "removed nodes/hyper/etc/ssh/sshd_config.d/\n"
        "removed nodes/hyper/etc/ssh/\n"
        "removed nodes/hyper/etc/\n")


def test_removes_a_symlink(fs, capsys):
    fs.create_symlink(NODE / "etc/localtime", "/usr/share/zoneinfo/UTC")

    forget(REPO, "hyper", ["/etc/localtime"])

    assert not (NODE / "etc/localtime").is_symlink()
    assert capsys.readouterr().out == "removed nodes/hyper/etc/localtime\n"


def test_keeps_a_symlink_to_a_directory_beside_the_files_forgotten(fs, capsys):
    fs.create_symlink(NODE / "etc/ssh/link", NODE / "home")

    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/etc/ssh/sshd_config.d/10-local.conf"])

    assert (NODE / "etc/ssh/link").is_symlink()
    assert (NODE / "home/alice/.ssh/config.tmpl").exists()
    assert "removed nodes/hyper/etc/ssh/\n" not in capsys.readouterr().out


def test_refuses_a_path_through_a_symlinked_directory_of_the_node(fs):
    fs.create_file("/outside/init.lua")
    fs.create_symlink(NODE / "etc/nvim", "/outside")

    with pytest.raises(Error, match="^not in node hyper: /etc/nvim/init.lua$"):
        forget(REPO, "hyper", ["/etc/nvim/init.lua"])
    assert Path("/outside/init.lua").exists()


@pytest.mark.parametrize("node, path, message", [
    ("laptop", "/etc/x", "no such node: laptop"),
    ("../hyper", "/etc/x", "no such node: ../hyper"),
    ("hyper", "/etc/nope", "not in node hyper: /etc/nope"),
    ("hyper", "etc/ssh/ssh_host_ed25519_key", "not in node hyper: etc/ssh/ssh_host_ed25519_key"),
    ("hyper", "/etc/ssh", "not in node hyper: /etc/ssh"),
    ("hyper", "/.meta", "not in node hyper: /.meta"),
    ("hyper", "/.hooks", "not in node hyper: /.hooks"),
    ("hyper", "/../hyper/.meta", "not in node hyper: /../hyper/.meta"),
])
def test_refuses(node, path, message):
    before = node_files()
    with pytest.raises(Error, match=f"^{message}$"):
        forget(REPO, node, ["/etc/ssh/ssh_host_ed25519_key", path])
    assert node_files() == before


def test_command(monkeypatch, fs, capsys):
    from dotfiles.cli import main

    fs.create_file(REPO / "secret_leaks.toml")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert main(["forget", "--dry-run", "hyper", "/etc/ssh/ssh_host_ed25519_key"]) == 0
    assert capsys.readouterr().out.startswith("removed nodes/hyper/etc/ssh/ssh_host_ed25519_key\n")


def test_removes_packages(capsys):
    (NODE / ".packages").write_text("niri\nparu\n")

    forget(REPO, "hyper", [], packages=["niri"])
    assert (NODE / ".packages").read_text() == "paru\n"
    forget(REPO, "hyper", [], packages=["paru"])
    assert not (NODE / ".packages").exists()
    assert capsys.readouterr().out == "removed package niri\nremoved package paru\n"


def test_refuses_a_package_not_listed():
    (NODE / ".packages").write_text("niri\n")
    with pytest.raises(Error, match="^not in node hyper: package nope$"):
        forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key"], packages=["niri", "nope"])
    assert (NODE / ".packages").read_text() == "niri\n"
    assert (NODE / "etc/ssh/ssh_host_ed25519_key").exists()


def test_dry_run_keeps_packages(capsys):
    (NODE / ".packages").write_text("niri\n")
    forget(REPO, "hyper", [], packages=["niri"], dry_run=True)
    assert (NODE / ".packages").read_text() == "niri\n"
