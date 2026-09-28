from pathlib import Path

import pytest

from dotfiles.render import render

HOSTS = ("hyper-lin", "echo-server", "unknown-host")


@pytest.fixture(scope="module")
def homes(tmp_path_factory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("homes")
    for host in HOSTS:
        render(host, base / host)
    return {host: base / host for host in HOSTS}


def text(homes, host, rel):
    return (homes[host] / rel).read_text()


def test_gitconfig(homes):
    on = text(homes, "hyper-lin", ".gitconfig")
    assert "    name  = Valentin Lukyanets\n    email = valikluks95@gmail.com\n" in on
    assert on.endswith("[color]\n    ui = auto\n")
    off = text(homes, "unknown-host", ".gitconfig")
    assert "    name  = \n    email = \n" in off


def test_ssh_config(homes):
    assert text(homes, "hyper-lin", ".ssh/config").endswith("Include config.d/*\n")
    assert (homes["unknown-host"] / ".ssh/config.d").is_dir()
    assert not (homes["unknown-host"] / ".ssh/config.d/.keep").exists()


def test_rbw(homes):
    assert text(homes, "hyper-lin", ".config/rbw/config.json").startswith(
        '{"email":"valikluks95@gmail.com","sso_id":null,'
    )
    assert not (homes["echo-server"] / ".config/rbw").exists()


def test_gates_and_modes(homes):
    def files(host):
        return {
            p.relative_to(homes[host]).as_posix(): oct(p.stat().st_mode & 0o777)[2:]
            for p in homes[host].rglob("*")
            if p.is_file()
        }

    assert files("unknown-host") == {
        ".gitconfig": "644",
        ".ssh/config": "644",
        ".config/environment.d/path.conf": "644",
    }
    assert oct((homes["hyper-lin"] / ".ssh").stat().st_mode & 0o777) == "0o700"


def test_authorized_keys(homes):
    keys = text(homes, "hyper-lin", ".ssh/authorized_keys").splitlines()[2:]
    assert [line.split()[-1] for line in keys] == ["nova-win", "nova-win-work"]
    assert all(line.startswith("ssh-ed25519 AAAA") for line in keys)
    assert not (homes["echo-server"] / ".ssh/authorized_keys").exists()


def test_deploy_hyper_lin_twice_is_silent_the_second_time():
    from dotfiles.render import deploy

    first = deploy("hyper-lin")
    assert "-> ~/.gitconfig (missing)" in first and "-> ~/.ssh (missing)" in first
    assert deploy("hyper-lin") == []
