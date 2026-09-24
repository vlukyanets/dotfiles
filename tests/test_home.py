"""The real home/ tree rendered for the real hosts: what the templates with
logic produce, pinned."""

import tempfile
import tomllib
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


def test_authorized_keys(homes):
    keys = text(homes, "hyper-lin", ".ssh/authorized_keys").splitlines()[2:]
    assert [line.split()[-1] for line in keys] == ["nova-win", "nova-win-work"]
    assert all(line.startswith("ssh-ed25519 AAAA") for line in keys)
    assert not (homes["echo-server"] / ".ssh/authorized_keys").exists()


def test_niri_and_layouts(homes):
    niri = text(homes, "hyper-lin", ".config/niri/config.kdl")
    assert niri.startswith("environment {\n")
    assert '    QT_QPA_PLATFORM "wayland"\n    // No GTK_IM_MODULE' in niri
    assert '    XMODIFIERS "@im=fcitx"\n    WAYLAND_DISPLAY' in niri
    assert 'layout "us,ru,ua,cn"' in niri
    assert (
        "        }\n\n        numlock\n    }\n\n    touchpad {" in niri
    )  # laptop: features.niri.numlock
    assert 'spawn-at-startup "fcitx5" "-d"\n\nhotkey-overlay' in niri
    switch = homes["hyper-lin"] / ".config/niri/switch-layout.sh"
    assert 'FCITX5_IMS=("keyboard-us" "keyboard-ru" "keyboard-ua" "pinyin")\n' in switch.read_text()
    assert oct(switch.stat().st_mode & 0o777) == "0o755"
    assert not (homes["echo-server"] / ".config/niri").exists()


def test_mimeapps(homes):
    mime = text(homes, "hyper-lin", ".config/mimeapps.list")
    assert "\n[Default Applications]\nx-scheme-handler/http=firefox.desktop\n" in mime
    assert "image/png=org.gnome.Loupe.desktop;feh.desktop\n" in mime
    assert mime.endswith("x-scheme-handler/claude-cli=claude-code-url-handler.desktop\n")


def test_fcitx5(homes):
    conf = homes["hyper-lin"] / ".config/fcitx5/conf"
    assert "\nBackend=Google\n" in (conf / "cloudpinyin.conf").read_text()
    assert "\nCloudPinyinEnabled=True\n" in (conf / "pinyin.conf").read_text()
    assert oct((conf / "pinyin.conf").stat().st_mode & 0o777) == "0o600"
    theme = homes["hyper-lin"] / ".local/share/fcitx5/themes/FluentDark-solid/panel.png"
    assert theme.read_bytes().startswith(b"\x89PNG")


def render_with_current(tmp_path, rel, text):
    current = tmp_path / "current"
    (current / rel).parent.mkdir(parents=True)
    (current / rel).write_text(text)
    render("hyper-lin", tmp_path / "out", current=current)
    return (tmp_path / "out" / rel).read_text()


def test_fcitx5_profile(homes, tmp_path):
    fresh = text(homes, "hyper-lin", ".config/fcitx5/profile")
    assert "DefaultIM=keyboard-us\n\n[Groups/0/Items/0]\n" in fresh
    assert "[Groups/0/Items/3]\n# Name\nName=pinyin\n# Layout\n# Layout=\n\n[GroupOrder]\n" in fresh
    assert fresh.endswith("[GroupOrder]\n0=Default\n")
    # What fcitx5 saved is kept while it is still listed...
    kept = render_with_current(
        tmp_path / "a",
        ".config/fcitx5/profile",
        fresh.replace("DefaultIM=keyboard-us", "DefaultIM=pinyin"),
    )
    assert kept == fresh.replace("DefaultIM=keyboard-us", "DefaultIM=pinyin")
    # ...and reset when it is not.
    reset = render_with_current(
        tmp_path / "b", ".config/fcitx5/profile", "[Groups/0]\nDefaultIM=mozc\n"
    )
    assert reset == fresh


def test_noctalia_settings_merge(homes, tmp_path):
    fresh = tomllib.loads(text(homes, "hyper-lin", ".local/state/noctalia/settings.toml"))
    assert fresh["shell"] == {"font_family": "FiraCode Nerd Font Propo"}
    assert fresh["theme"] == {
        "source": "community",
        "mode": "dark",
        "community_palette": "Cyberpunk",
    }
    assert fresh["bar"]["default"]["font_scale"] == 1.1
    current = (
        'config_version = 12\nwallpaper = "/tmp/w.png"\n'
        '[shell]\nfont_family = "Mono"\nanimation = false\n'
        '[plugins]\nenabled = ["clock"]\n'
    )
    merged = tomllib.loads(
        render_with_current(tmp_path, ".local/state/noctalia/settings.toml", current)
    )
    assert merged["config_version"] == 14  # the repo's keys win
    assert merged["shell"] == {"font_family": "FiraCode Nerd Font Propo", "animation": False}
    assert merged["wallpaper"] == "/tmp/w.png"  # noctalia's own keys survive
    assert merged["plugins"] == {"enabled": ["clock"]}
    # Deploying again over our own output changes nothing.
    again = render_with_current(
        tmp_path / "again",
        ".local/state/noctalia/settings.toml",
        (tmp_path / "out/.local/state/noctalia/settings.toml").read_text(),
    )
    assert again == (tmp_path / "out/.local/state/noctalia/settings.toml").read_text()


def test_deploy_hyper_lin_twice_is_silent_the_second_time():
    from dotfiles.render import deploy

    first = deploy("hyper-lin")
    assert "-> ~/.zshrc (missing)" in first and "-> ~/.ssh (missing)" in first
    assert deploy("hyper-lin") == []
