"""The real home/ tree rendered for the real hosts: what the templates with
logic produce, pinned."""

import tempfile
from pathlib import Path

import pytest

from dotfiles.render import render

HOSTS = ("hyper-lin", "echo-server", "unknown-host")


@pytest.fixture(scope="module")
def homes(tmp_path_factory) -> dict[str, Path]:
    base = tmp_path_factory.mktemp("homes")
    for host in HOSTS:
        render(host, base / host)
    homes = {host: base / host for host in HOSTS}
    homes["HOME"] = Path.home()  # what the templates saw as `home`
    return homes


def text(homes, host, rel):
    return (homes[host] / rel).read_text()


def test_gitconfig(homes):
    on = text(homes, "hyper-lin", ".gitconfig")
    assert "    name  = Valentin Lukyanets\n    email = valikluks95@gmail.com\n" in on
    assert "    ui = auto\n\n# Gated on features.cli_tools" in on
    assert "    colorMoved = default\n\n# Exactly what `git lfs install`" in on
    assert on.endswith("    process = git-lfs filter-process\n    required = true\n")
    off = text(homes, "unknown-host", ".gitconfig")
    assert "    name  = \n    email = \n" in off
    assert off.endswith("[color]\n    ui = auto\n")


def test_zshrc(homes):
    full = text(homes, "hyper-lin", ".zshrc")
    assert '[[ -n "$ZSH_VERSION" ]] || return\n\n# Enable Powerlevel10k' in full
    assert "source ~/.p10k.zsh\n\n# ~/.local/bin first" in full
    assert 'SUDO_CMD:-sudo}"\n\n# The user session gets this' in full
    assert 'ssh-agent.socket}"\n\n# virsh/virt-install' in full
    assert '"${LIBVIRT_DEFAULT_URI:-qemu:///system}"\n\nif command -v zoxide' in full
    assert 'eval "$(fzf --zsh)"\nfi\n\nif command -v fnm' in full
    assert 'eval "$(fnm env --use-on-cd)"\nfi\n\n# "command not found"' in full
    # echo-server: zsh and ssh_agent on, libvirt and fnm off.
    server = text(homes, "echo-server", ".zshrc")
    assert 'ssh-agent.socket}"\n\nif command -v zoxide' in server
    assert 'eval "$(fzf --zsh)"\nfi\n\n# "command not found"' in server
    assert "LIBVIRT" not in server and "fnm" not in server
    assert not (homes["unknown-host"] / ".zshrc").exists()


def test_ssh_config(homes):
    assert text(homes, "hyper-lin", ".ssh/config").endswith(
        "Include config.d/*\n\nHost *\n"
        "    # Add a key to the running ssh-agent on first use, so a passphrase is\n"
        "    # asked for once per login rather than once per connection.\n"
        "    AddKeysToAgent yes\n"
    )
    assert text(homes, "unknown-host", ".ssh/config").endswith("Include config.d/*\n")
    assert (homes["unknown-host"] / ".ssh/config.d").is_dir()
    assert not (homes["unknown-host"] / ".ssh/config.d/.keep").exists()


def test_sccache(homes):
    assert text(homes, "hyper-lin", ".config/sccache/config").endswith(
        '# here so sccache\'s own default applies.\n\n[cache.disk]\nsize = "20G"\n'
    )


def test_one_line_values(homes):
    assert "vim.g.have_nerd_font = true\n" in text(homes, "hyper-lin", ".config/nvim/init.lua")
    assert "vim.g.have_nerd_font = false\n" in text(homes, "echo-server", ".config/nvim/init.lua")
    assert text(homes, "hyper-lin", ".config/rbw/config.json").startswith(
        '{"email":"valikluks95@gmail.com","sso_id":null,'
    )
    home = str(homes["HOME"])
    assert home.startswith(tempfile.gettempdir())  # isolated, not the real home
    assert f"GOPATH={home}/.local/share/go\nGOBIN={home}/.local/bin\n" in text(
        homes, "hyper-lin", ".config/go/env"
    )


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
    hyper = files("hyper-lin")
    assert hyper[".config/htop/htoprc"] == "600"
    assert hyper[".config/VeraCrypt/Configuration.xml"] == "600"
    assert oct((homes["hyper-lin"] / ".ssh").stat().st_mode & 0o777) == "0o700"
    assert ".config/rbw/config.json" in hyper
    assert ".config/rbw/config.json" not in files("echo-server")
