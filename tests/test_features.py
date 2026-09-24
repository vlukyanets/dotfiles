"""The features in dotfiles/features/, each against a fake machine: every
command faked, root's files written under SYSROOT (conftest.machine)."""

import grp
import importlib
import os
import pwd
import tomllib

import pytest

from dotfiles import engine, platforms
from dotfiles.config import ROOT
from dotfiles.platforms.arch import Arch

ME = pwd.getpwuid(os.geteuid()).pw_name


def defaults(**features) -> dict:
    """The schema's config with FEATURES' settings changed."""
    cfg = tomllib.loads((ROOT / "dotfiles/defaults.toml").read_text())
    for name, settings in features.items():
        cfg["features"][name].update(settings)
    return cfg


def feature(name: str, cfg: dict | None = None):
    """Feature NAME and its Arch strategy."""
    cfg = cfg or defaults()
    module = importlib.import_module(f"dotfiles.features.{name}")
    instance = platforms.classes(module)[-1](cfg)
    return instance, instance.strategy(Arch(cfg))


def apply(name: str, cfg: dict | None = None) -> None:
    instance, strategy = feature(name, cfg)
    instance.apply(strategy)


def running(machine, *units: str) -> None:
    """UNITS answer enabled and active from now on."""
    for unit in units:
        machine.answers[("systemctl", "is-enabled", unit)] = (0, "enabled")
        machine.answers[("systemctl", "is-active", unit)] = (0, "active")


def write(name: str, text: str):
    real = engine.path(name)
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(text)
    return real


def test_packages_that_depend_on_settings():
    assert "fcitx5-chinese-addons" not in feature("fcitx5")[1].packages()
    assert feature("rbw")[1].packages() == []
    gaming, strategy = feature("gaming")
    assert strategy.packages() == []  # no multilib: nothing half-installed
    with pytest.raises(engine.Failed, match="set features.pacman.multilib = true"):
        gaming.apply(strategy)

    cfg = defaults(locale={"languages": ["english", "chinese"]}, pacman={"enabled": True})
    cfg["features"]["pacman"]["multilib"] = True
    cfg["secrets"]["backend"] = "rbw"
    assert "fcitx5-chinese-addons" in feature("fcitx5", cfg)[1].packages()
    assert feature("rbw", cfg)[1].packages() == ["rbw", "pinentry"]
    gaming, strategy = feature("gaming", cfg)
    assert "steam" in strategy.packages()
    gaming.apply(strategy)


# Batch 2: a package and its unit.


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("bluetooth", "bluetooth.service"),
        ("fwupd", "fwupd-refresh.timer"),
        ("btrfs_scrub", "btrfs-scrub@-.timer"),
        ("paccache", "paccache.timer"),
        ("yubikey", "pcscd.socket"),
        ("timesyncd", "systemd-timesyncd.service"),
    ],
)
def test_a_package_and_its_unit(machine, name, unit):
    apply(name)
    assert machine.calls[-1] == ["systemctl", "enable", "--now", unit]


def test_docker_joins_the_group(machine, monkeypatch):
    monkeypatch.setattr(grp, "getgrnam", lambda name: grp.struct_group((name, "x", 970, [])))
    apply("docker")
    assert machine.calls[-1] == ["usermod", "-aG", "docker", ME]


def test_pkgfile_seeds_its_database_once(machine, capsys):
    apply("pkgfile")
    assert machine.calls[-1] == ["pkgfile", "-u"]
    assert capsys.readouterr().out.endswith("-> pkgfile database created\n")
    write("/var/cache/pkgfile/core.files", "")
    machine.calls.clear()
    apply("pkgfile")
    assert ["pkgfile", "-u"] not in machine.calls


def test_pkgfile_defers_a_failed_download(machine, monkeypatch):
    monkeypatch.setattr(engine, "sleep", lambda seconds: None)
    machine.answers[("pkgfile", "-u")] = (1, "")
    with pytest.raises(engine.Deferred, match="pkgfile database"):
        apply("pkgfile")


def test_tailscale_sets_the_operator_once(machine, capsys):
    apply("tailscale")
    assert machine.calls[-1] == ["tailscale", "set", f"--operator={ME}"]
    assert capsys.readouterr().out.endswith(f"-> tailscale operator = {ME}\n")
    machine.answers[("tailscale", "debug", "prefs")] = (0, f'{{"OperatorUser": "{ME}"}}')
    running(machine, "tailscaled.service")
    apply("tailscale")
    assert capsys.readouterr().out == ""


# Batch 3: system configuration.


def test_locale(machine, capsys):
    gen = write("/etc/locale.gen", "#de_DE.UTF-8 UTF-8\n#en_US.UTF-8 UTF-8  \n")
    write("/etc/mkinitcpio.conf", "HOOKS=(base systemd sd-vconsole)\n")
    cfg = defaults(locale={"timezone": "Europe/Kyiv"})
    cfg["features"]["locale"]["console"]["font"] = "ter-v20n"
    machine.answers[("systemctl", "restart", "systemd-vconsole-setup.service")] = (1, "")
    apply("locale", cfg)
    assert gen.read_text() == "#de_DE.UTF-8 UTF-8\nen_US.UTF-8 UTF-8\n"
    assert engine.path("/etc/locale.conf").read_text() == "LANG=en_US.UTF-8\n"
    assert engine.path("/etc/vconsole.conf").read_text() == "KEYMAP=us\nFONT=ter-v20n\n"
    assert os.readlink(engine.path("/etc/localtime")) == "/usr/share/zoneinfo/Europe/Kyiv"
    commands = [c[0] for c in machine.calls if c[0] not in ("install", "ln")]
    assert commands == ["locale-gen", "systemctl", "hwclock"]  # a failed restart is fine
    assert [n.split(" — ")[0] for n in engine.notices] == [
        "console font ter-v20n is not in /usr/share/kbd/consolefonts",
        "console font changed",
    ]
    capsys.readouterr()
    machine.calls.clear()
    apply("locale", cfg)
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_oomd(machine, capsys):
    apply("oomd")
    assert engine.path("/etc/systemd/system/-.slice.d/10-oomd.conf").exists()
    commands = [
        c for c in machine.calls if c[0] == "systemctl" and c[1] not in ("is-enabled", "is-active")
    ]
    assert commands == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "try-restart", "systemd-oomd.service"],
        ["systemctl", "enable", "--now", "systemd-oomd.service"],
    ]
    capsys.readouterr()
    running(machine, "systemd-oomd.service")
    apply("oomd")
    assert capsys.readouterr().out == ""


def test_sshd(machine, capsys):
    running(machine, "sshd.service")
    apply("sshd", defaults(sshd={"password_auth": False}))
    conf = engine.path("/etc/ssh/sshd_config.d/dotfiles.conf")
    assert conf.read_text() == "PasswordAuthentication no\nPermitRootLogin prohibit-password\n"
    assert machine.calls[-3] == ["systemctl", "reload", "sshd.service"]
    assert engine.notices[0].startswith("sshd: password login is being turned off")
    capsys.readouterr()
    engine.notices.clear()
    apply("sshd", defaults(sshd={"password_auth": False}))
    assert capsys.readouterr().out == ""
    assert engine.notices == []


def test_resolved(machine, capsys):
    running(machine, "systemd-resolved.service", "NetworkManager.service")
    machine.answers[("nm-online", "-s", "-q", "-t", "30")] = (1, "")
    apply("resolved")
    assert os.readlink(engine.path("/etc/resolv.conf")) == "/run/systemd/resolve/stub-resolv.conf"
    assert ["systemctl", "restart", "NetworkManager.service"] in machine.calls
    assert engine.notices[0].startswith("NetworkManager is still not up")
    capsys.readouterr()
    machine.calls.clear()
    apply("resolved")
    assert capsys.readouterr().out == ""
    assert ["systemctl", "restart", "NetworkManager.service"] not in machine.calls


def test_zram(machine, capsys):
    unit = "systemd-zram-setup@zram0.service"
    machine.answers[("sysctl", "-n", "vm.swappiness")] = (0, "60")
    apply("zram", defaults(zram={"swappiness": 180}))
    assert engine.path("/etc/systemd/zram-generator.conf").read_text() == (
        "[zram0]\nzram-size = min(ram / 2, 4096)\ncompression-algorithm = zstd\n"
        "swap-priority = 100\n"
    )
    assert ["systemctl", "restart", unit] in machine.calls
    assert ["sysctl", "-qw", "vm.swappiness=180"] in machine.calls
    assert not any("watermark" in " ".join(c) for c in machine.calls)
    capsys.readouterr()
    running(machine, unit)
    machine.answers[("sysctl", "-n", "vm.swappiness")] = (0, "180")
    machine.answers[("sysctl", "-n", "vm.page-cluster")] = (0, "0")
    apply("zram", defaults(zram={"swappiness": 180}))
    assert capsys.readouterr().out == ""


def test_thp(machine, capsys):
    live = write("/sys/kernel/mm/transparent_hugepage/enabled", "always [madvise] never\n")
    apply("thp")
    conf = "/etc/tmpfiles.d/thp.conf"
    assert engine.path(conf).read_text() == (
        "w /sys/kernel/mm/transparent_hugepage/enabled - - - - always\n"
    )
    assert machine.calls[-1] == ["systemd-tmpfiles", "--create", conf]
    capsys.readouterr()
    live.write_text("[always] madvise never\n")
    machine.calls.clear()
    apply("thp")
    assert capsys.readouterr().out == ""
    assert machine.calls == []
