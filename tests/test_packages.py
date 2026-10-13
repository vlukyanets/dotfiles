"""Tests for the packages of a node, with fake os-release and a fake pacman and dpkg."""

import subprocess
from pathlib import Path

import pytest

from dotfiles import packages
from dotfiles.add import Error

NODE = Path("/repo/nodes/hyper")
ARCH = 'NAME="Arch Linux"\nID=arch\n'


@pytest.fixture
def machine(fs, monkeypatch):
    """An Arch machine with paru, base and paru installed; the commands run are noted."""
    fs.create_file("/etc/os-release", contents=ARCH)
    fs.create_dir(NODE)
    ran = []
    output = {"pacman": "base\nparu\n",
              "dpkg-query": "ii  base\nrc  removed\nii  vim\n",
              "apt-mark": "vim\ngit\nbase\n"}

    def run(command, **kwargs):
        ran.append(command)
        return subprocess.CompletedProcess(command, 0, output.get(command[0], ""), "")

    monkeypatch.setattr(packages.subprocess, "run", run)
    monkeypatch.setattr(packages.shutil, "which", lambda name: f"/usr/bin/{name}")
    return ran


@pytest.mark.parametrize("os_release, expected", [
    (ARCH, "arch"),
    ("ID=endeavouros\nID_LIKE=arch\n", "arch"),
    ('ID=debian\nVERSION_ID="12"\n', "debian"),
    ('ID=ubuntu\nID_LIKE="ubuntu debian"\n', "debian"),
])
def test_family(fs, os_release, expected):
    fs.create_file("/etc/os-release", contents=os_release)
    assert packages.family() == expected


def test_family_from_usr_lib(fs):
    fs.create_file("/usr/lib/os-release", contents=ARCH)
    assert packages.family() == "arch"


@pytest.mark.parametrize("os_release, name", [("ID=fedora\n", "fedora"), (None, "one without /etc/os-release")])
def test_family_unknown_is_an_error(fs, os_release, name):
    if os_release is not None:
        fs.create_file("/etc/os-release", contents=os_release)
    with pytest.raises(Error, match=f"^only Arch, Debian and the distributions like them are supported, not {name}$"):
        packages.family()


@pytest.mark.parametrize("command", [["add", "hyper", "/etc/x"], ["install", "hyper"],
                                     ["restore", "hyper"], ["status", "hyper"]])
def test_commands_on_the_machine_refuse_another_distribution(fs, monkeypatch, capsys, command):
    from dotfiles.cli import main

    fs.create_file("/etc/os-release", contents="ID=fedora\n")
    fs.create_file("/repo/secret_leaks.toml")
    monkeypatch.setenv("DOTFILES_REPO", "/repo")
    monkeypatch.setattr("os.geteuid", lambda: 1000)
    assert main(command) == 1
    assert "not fedora" in capsys.readouterr().err


def test_installed_on_arch(machine):
    assert packages.installed() == {"base", "paru"}
    assert machine == [["pacman", "-Qq"]]


def test_installed_on_debian(machine, fs):
    Path("/etc/os-release").write_text("ID=debian\n")
    assert packages.installed() == {"base", "vim"}
    assert machine == [["dpkg-query", "-W", "-f=${db:Status-Abbrev} ${Package}\n"]]


def test_explicit_on_arch(machine):
    assert packages.explicit() == {"base", "paru"}
    assert machine == [["pacman", "-Qqe"]]


def test_explicit_on_debian(machine, fs):
    Path("/etc/os-release").write_text("ID=debian\n")
    assert packages.explicit() == {"base", "git", "vim"}
    assert machine == [["apt-mark", "showmanual"]]


def test_extra_lists_what_the_list_lacks_sorted(machine):
    (NODE / ".packages").write_text("base\nniri\n")
    machine.clear()
    Path("/etc/os-release").write_text("ID=debian\n")

    assert packages.extra(NODE) == ["git", "vim"]


def test_extra_is_empty_without_a_list(machine):
    assert packages.extra(NODE) == []
    assert machine == []


def test_install_command(machine, monkeypatch):
    assert packages.install_command(["a"]) == ["paru", "-S", "--needed", "a"]
    monkeypatch.setattr(packages.shutil, "which", lambda name: None)
    assert packages.install_command(["a"]) == ["sudo", "pacman", "-S", "--needed", "a"]
    Path("/etc/os-release").write_text("ID=debian\n")
    assert packages.install_command(["a", "b"]) == ["sudo", "apt-get", "install", "a", "b"]


def test_plan_installs_what_is_missing(machine):
    (NODE / ".packages").write_text("base\nniri\n\nwaybar\n")

    [(line, action)] = packages.plan(NODE, Path("/"))
    assert line == "installed packages niri waybar"
    action()

    assert machine[-1] == ["paru", "-S", "--needed", "niri", "waybar"]


def test_plan_is_empty_when_nothing_is_missing(machine):
    (NODE / ".packages").write_text("base\n")
    assert packages.plan(NODE, Path("/")) == []


def test_plan_is_empty_without_a_list(machine):
    assert packages.plan(NODE, Path("/")) == []
    assert machine == []


def test_plan_skips_another_root(machine):
    (NODE / ".packages").write_text("niri\n")
    [(line, _)] = packages.plan(NODE, Path("/srv"))
    assert line == "skipped packages (the root is /srv)"
    assert machine == []


def test_write_sorts_and_removes_an_empty_list(machine):
    packages.write(NODE, ["b", "a", "b"])
    assert (NODE / ".packages").read_text() == "a\nb\n"
    packages.write(NODE, [])
    assert not (NODE / ".packages").exists()


def test_run_reports_a_failure(monkeypatch):
    monkeypatch.setattr(packages.subprocess, "run",
                        lambda command, **kwargs: subprocess.CompletedProcess(command, 1))
    with pytest.raises(Error, match="^paru -S --needed a: exited with 1$"):
        packages.run(["paru", "-S", "--needed", "a"])


def test_run_without_the_tool(monkeypatch):
    def missing(command, **kwargs):
        raise FileNotFoundError(command[0])
    monkeypatch.setattr(packages.subprocess, "run", missing)
    with pytest.raises(Error, match="^dpkg-query is needed for packages$"):
        packages.run(["dpkg-query", "-W"])


def test_problems_names_each_line_of_more_than_one_word(fs):
    fs.create_dir(NODE)
    assert packages.problems(NODE) == []
    (NODE / ".packages").write_text("base\n\nniri git\n")
    assert packages.problems(NODE) == [f"{NODE}/.packages:3: not one package name"]
