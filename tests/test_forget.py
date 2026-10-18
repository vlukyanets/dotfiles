"""Tests for dotfiles forget, on a fake filesystem."""

import os
from pathlib import Path

import pytest

from dotfiles.add import Error
from dotfiles.forget import forget

REPO = Path("/repo")
HOST = REPO / "hosts/hyper"


def host_files():
    return sorted(str(p.relative_to(HOST)) for p in HOST.rglob("*"))


@pytest.fixture(autouse=True)
def host_dir(fs):
    fs.create_file(HOST / "etc/ssh/sshd_config.d/10-local.conf")
    fs.create_file(HOST / "etc/ssh/ssh_host_ed25519_key")
    fs.create_file(HOST / "home/alice/.ssh/config.tmpl")
    fs.create_file(HOST / ".meta", contents=(
        "0600 root:root etc/ssh/ssh_host_ed25519_key\n"
        "0700 alice:alice home/alice/.ssh/\n"
        "0600 alice:alice home/alice/.ssh/config.tmpl\n"
    ))


def test_removes_the_file_and_its_line(capsys):
    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key"])

    assert not (HOST / "etc/ssh/ssh_host_ed25519_key").exists()
    assert (HOST / "etc/ssh/sshd_config.d/10-local.conf").exists()
    assert (HOST / ".meta").read_text() == (
        "0700 alice:alice home/alice/.ssh/\n"
        "0600 alice:alice home/alice/.ssh/config.tmpl\n")
    assert capsys.readouterr().out == (
        "removed hosts/hyper/etc/ssh/ssh_host_ed25519_key\n"
        "meta: removed etc/ssh/ssh_host_ed25519_key\n")


def test_removes_a_template_and_the_directories_left_empty(capsys):
    forget(REPO, "hyper", ["/home/alice/.ssh/config"])

    assert not (HOST / "home").exists()
    assert (HOST / ".meta").read_text() == "0600 root:root etc/ssh/ssh_host_ed25519_key\n"
    assert capsys.readouterr().out == (
        "removed hosts/hyper/home/alice/.ssh/config.tmpl\n"
        "meta: removed home/alice/.ssh/config.tmpl\n"
        "removed hosts/hyper/home/alice/.ssh/\n"
        "meta: removed home/alice/.ssh/\n"
        "removed hosts/hyper/home/alice/\n"
        "removed hosts/hyper/home/\n")


def test_removes_the_meta_file_once_it_is_empty():
    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/home/alice/.ssh/config"])

    assert host_files() == ["etc", "etc/ssh", "etc/ssh/sshd_config.d",
                            "etc/ssh/sshd_config.d/10-local.conf"]


def test_dry_run_changes_nothing(capsys):
    before = host_files(), (HOST / ".meta").read_text()

    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/etc/ssh/sshd_config.d/10-local.conf",
                           "/etc/ssh/sshd_config.d/10-local.conf"], dry_run=True)

    assert (host_files(), (HOST / ".meta").read_text()) == before
    assert capsys.readouterr().out == (
        "removed hosts/hyper/etc/ssh/ssh_host_ed25519_key\n"
        "meta: removed etc/ssh/ssh_host_ed25519_key\n"
        "removed hosts/hyper/etc/ssh/sshd_config.d/10-local.conf\n"
        "removed hosts/hyper/etc/ssh/sshd_config.d/\n"
        "removed hosts/hyper/etc/ssh/\n"
        "removed hosts/hyper/etc/\n")


def test_removes_a_symlink(fs, capsys):
    fs.create_symlink(HOST / "etc/localtime", "/usr/share/zoneinfo/UTC")

    forget(REPO, "hyper", ["/etc/localtime"])

    assert not (HOST / "etc/localtime").is_symlink()
    assert capsys.readouterr().out == "removed hosts/hyper/etc/localtime\n"


def test_keeps_a_symlink_to_a_directory_beside_the_files_forgotten(fs, capsys):
    fs.create_symlink(HOST / "etc/ssh/link", HOST / "home")

    forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key", "/etc/ssh/sshd_config.d/10-local.conf"])

    assert (HOST / "etc/ssh/link").is_symlink()
    assert (HOST / "home/alice/.ssh/config.tmpl").exists()
    assert "removed hosts/hyper/etc/ssh/\n" not in capsys.readouterr().out


def test_refuses_a_path_through_a_symlinked_directory_of_the_host(fs):
    fs.create_file("/outside/init.lua")
    fs.create_symlink(HOST / "etc/nvim", "/outside")

    with pytest.raises(Error, match="^not in host hyper: /etc/nvim/init.lua$"):
        forget(REPO, "hyper", ["/etc/nvim/init.lua"])
    assert Path("/outside/init.lua").exists()


@pytest.mark.parametrize("host, path, message", [
    ("laptop", "/etc/x", "no such host: laptop"),
    ("../hyper", "/etc/x", "no such host: ../hyper"),
    ("hyper", "/etc/nope", "not in host hyper: /etc/nope"),
    ("hyper", "etc/ssh/ssh_host_ed25519_key", "not in host hyper: etc/ssh/ssh_host_ed25519_key"),
    ("hyper", "/etc/ssh", "not in host hyper: /etc/ssh"),
    ("hyper", "/.meta", "not in host hyper: /.meta"),
    ("hyper", "/.hooks", "not in host hyper: /.hooks"),
    ("hyper", "/../hyper/.meta", "not in host hyper: /../hyper/.meta"),
])
def test_refuses(host, path, message):
    before = host_files()
    with pytest.raises(Error, match=f"^{message}$"):
        forget(REPO, host, ["/etc/ssh/ssh_host_ed25519_key", path])
    assert host_files() == before


def test_command(monkeypatch, fs, capsys):
    from dotfiles.cli import main

    fs.create_file(REPO / "secret_leaks.toml")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    assert main(["forget", "--dry-run", "hyper", "/etc/ssh/ssh_host_ed25519_key"]) == 0
    assert capsys.readouterr().out.startswith("removed hosts/hyper/etc/ssh/ssh_host_ed25519_key\n")


def test_removes_packages(capsys):
    (HOST / ".packages").write_text("niri\nparu\n")

    forget(REPO, "hyper", [], packages=["niri"])
    assert (HOST / ".packages").read_text() == "paru\n"
    forget(REPO, "hyper", [], packages=["paru"])
    assert not (HOST / ".packages").exists()
    assert capsys.readouterr().out == "removed package niri\nremoved package paru\n"


def test_refuses_a_package_not_listed():
    (HOST / ".packages").write_text("niri\n")
    with pytest.raises(Error, match="^not in host hyper: package nope$"):
        forget(REPO, "hyper", ["/etc/ssh/ssh_host_ed25519_key"], packages=["niri", "nope"])
    assert (HOST / ".packages").read_text() == "niri\n"
    assert (HOST / "etc/ssh/ssh_host_ed25519_key").exists()


def test_dry_run_keeps_packages(capsys):
    (HOST / ".packages").write_text("niri\n")
    forget(REPO, "hyper", [], packages=["niri"], dry_run=True)
    assert (HOST / ".packages").read_text() == "niri\n"
