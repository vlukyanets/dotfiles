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


# Batch 4: snapper and its pair.

SNAPPER = ("snapper", "-c", "root")
PRE = (*SNAPPER, "create", "-t", "pre", "-c", "number", "-d", "dotfiles apply", "-p")
CONFIG = {
    "TIMELINE_CREATE": "no",
    "NUMBER_LIMIT": "10",
    "NUMBER_LIMIT_IMPORTANT": "5",
    "ALLOW_USERS": ME,
    "SYNC_ACL": "yes",
}


def test_snapper(machine, capsys):
    machine.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, "btrfs\n")
    cfg = defaults(snapper={"important_packages": ["linux-zen"]})
    apply("snapper", cfg)
    mutations = [c for c in machine.calls if c[0] == "snapper" and "get-config" not in c]
    assert mutations == [
        [*SNAPPER, "create-config", "/"],
        [*SNAPPER, "set-config", *(f"{k}={v}" for k, v in CONFIG.items())],
    ]
    assert ["chmod", "750", "/.snapshots"] in machine.calls
    assert engine.path("/etc/snap-pac.ini").read_text() == (
        '[root]\nimportant_packages = ["linux-zen"]\nimportant_commands = []\n'
    )
    capsys.readouterr()

    write("/etc/snapper/configs/root", "")
    csv = "key,value\n" + "".join(f"{k},{v}\n" for k, v in CONFIG.items())
    machine.answers[("snapper", "--machine-readable", "csv", "-c", "root", "get-config")] = (0, csv)
    running(machine, "snapper-cleanup.timer")
    machine.calls.clear()
    apply("snapper", cfg)
    assert capsys.readouterr().out == ""
    assert not [c for c in machine.calls if c[0] not in ("findmnt", "snapper", "systemctl")]


def test_snapper_needs_btrfs(machine):
    machine.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, "ext4\n")
    with pytest.raises(engine.Failed, match="^/ is ext4, snapper needs a btrfs root$"):
        apply("snapper")


def test_snapper_steps_aside_for_a_mounted_snapshots_dir(machine):
    machine.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, "btrfs\n")
    machine.answers[("findmnt", "-n", "/.snapshots")] = (0, "/.snapshots /dev/x[/@snapshots]\n")
    apply("snapper")
    order = [c[:2] for c in machine.calls if c[0] in ("umount", "rmdir", "mount", "mkdir")]
    assert order == [["umount", "/.snapshots"], ["rmdir", "/.snapshots"], ["mkdir", "/.snapshots"],
                     ["mount", "/.snapshots"]]  # fmt: skip


@pytest.fixture
def snapper(machine):
    machine.answers[(*SNAPPER, "list")] = (0, "# | Type | Date\n0 | single |\n")
    machine.answers[PRE] = (0, "42\n")
    return machine


def test_the_pair_is_taken_only_around_package_changes(snapper, capsys):
    snap, strategy = feature("snapper", defaults(snapper={"important_packages": ["linux-zen"]}))
    log = write("/var/log/pacman.log", "[x] [ALPM] installed linux-zen (1)\n")
    with snap.session(strategy):
        assert os.environ["SNAP_PAC_SKIP"] == "y"
        assert not [c for c in snapper.calls if c[3:4] == ["create"]]  # nothing changed yet
        platforms.transaction()
        platforms.transaction()
        with log.open("a") as f:
            f.write("[y] [ALPM] upgraded linux-zen (2)\n")
    assert "SNAP_PAC_SKIP" not in os.environ
    creates = [c for c in snapper.calls if c[3:4] in (["create"], ["modify"])]
    assert creates == [
        list(PRE),
        [*SNAPPER, "modify", "-u", "important=yes", "42"],
        [*SNAPPER, "create", "-t", "post", "--pre-number", "42", "-c", "number", "-d",
         "dotfiles apply", "-u", "important=yes"],
    ]  # fmt: skip
    assert capsys.readouterr().out == (
        "-> snapper pre snapshot #42\n-> snapper post snapshot for #42 (important)\n"
    )


def test_no_pair_without_a_change_a_usable_snapper_or_on_a_dry_run(snapper, monkeypatch):
    snap, strategy = feature("snapper")
    with snap.session(strategy):
        pass  # nothing changed
    assert not [c for c in snapper.calls if c[3:4] == ["create"]]

    snapper.answers[(*SNAPPER, "list")] = (1, "")  # ALLOW_USERS not set yet
    with snap.session(strategy):
        assert "SNAP_PAC_SKIP" not in os.environ
        platforms.transaction()
    assert not [c for c in snapper.calls if c[3:4] == ["create"]]

    snapper.answers[(*SNAPPER, "list")] = (0, "0 | single |\n")
    monkeypatch.setattr(engine, "DRY_RUN", True)
    with snap.session(strategy):
        platforms.transaction()
    assert not [c for c in snapper.calls if c[3:4] == ["create"]]


def test_a_failed_apply_still_gets_its_post(snapper):
    snap, strategy = feature("snapper")
    with pytest.raises(RuntimeError), snap.session(strategy):
        platforms.transaction()
        raise RuntimeError
    assert snapper.calls[-1][3:7] == ["create", "-t", "post", "--pre-number"]


# Batch 4: boot and disks.

UUID = "0a1b2c3d-1111-2222-3333-444455556666"


@pytest.mark.parametrize(
    ("before", "after"),
    [
        (f"rd.luks.name={UUID}=root rw", f"rd.luks.name={UUID}=root rw rd.luks.options={UUID}:discard"),
        (f"rd.luks.name={UUID}=root rd.luks.options={UUID}:tpm2-device=auto quiet",
         f"rd.luks.name={UUID}=root rd.luks.options={UUID}:tpm2-device=auto,discard quiet"),
        (f"rd.luks.name={UUID}=root rd.luks.options={UUID}:discard", None),  # already
        ("root=/dev/sda2 rw", "no rd.luks.name"),
    ],
)  # fmt: skip
def test_with_discard(before, after):
    from dotfiles.features.luks_discard import with_discard

    result = with_discard(before)
    if after is None:
        assert result == before
    elif after == "no rd.luks.name":
        assert result is None
    else:
        assert result == after


def test_luks_discard(machine, capsys):
    write("/etc/mkinitcpio.conf", "HOOKS=(base systemd sd-encrypt)\n")
    cmdline = write("/etc/kernel/cmdline", f"rd.luks.name={UUID}=root rw\n")
    apply("luks_discard")
    assert cmdline.read_text() == f"rd.luks.name={UUID}=root rw rd.luks.options={UUID}:discard\n"
    assert engine.notices[0].startswith("LUKS discard enabled")
    capsys.readouterr()
    apply("luks_discard")
    assert capsys.readouterr().out == ""
    assert len(engine.notices) == 1


@pytest.mark.parametrize(
    ("setup", "notice"),
    [
        ({"/etc/mkinitcpio.conf": "HOOKS=(base udev encrypt)\n"}, "no sd-encrypt hook"),
        ({"/etc/mkinitcpio.conf": "HOOKS=(base sd-encrypt)\n"}, "/etc/kernel/cmdline does not exist"),
        ({"/etc/mkinitcpio.conf": "HOOKS=(sd-encrypt)\n", "/etc/kernel/cmdline": "rw\n"},
         "no rd.luks.name="),
    ],
)  # fmt: skip
def test_luks_discard_says_what_to_do_by_hand(machine, setup, notice):
    for name, text in setup.items():
        write(name, text)
    apply("luks_discard")
    assert notice in engine.notices[0]
    assert not [c for c in machine.calls if c[0] == "install"]


def test_plymouth(machine, capsys):
    conf = write("/etc/mkinitcpio.conf", "MODULES=()\nHOOKS=(base systemd autodetect)\n")
    apply("plymouth")
    assert conf.read_text() == "MODULES=()\nHOOKS=(base systemd plymouth autodetect)\n"
    assert machine.calls[-1] == ["plymouth-set-default-theme", "-R", "bgrt"]
    assert "quiet splash" in engine.notices[0]
    capsys.readouterr()
    machine.answers[("plymouth-set-default-theme",)] = (0, "bgrt\n")
    machine.calls.clear()
    apply("plymouth")
    assert capsys.readouterr().out == ""
    assert ["plymouth-set-default-theme", "-R", "bgrt"] not in machine.calls


def test_plymouth_goes_after_udev_without_systemd(machine):
    conf = write("/etc/mkinitcpio.conf", "HOOKS=(base udev encrypt)\n")
    apply("plymouth")
    assert conf.read_text() == "HOOKS=(base udev plymouth encrypt)\n"


@pytest.fixture
def btrfs(machine):
    machine.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, "btrfs\n")
    machine.answers[("findmnt", "-no", "UUID", "/")] = (0, "f00d\n")
    machine.answers[("findmnt", "-no", "SOURCE", "/")] = (0, "/dev/mapper/root[/@]\n")
    machine.answers[("btrfs", "subvolume", "list", "/")] = (0, "ID 256 gen 9 top level 5 path @\n")
    return machine


def test_swap(btrfs, capsys):
    cfg = defaults(swap={"size": "20g"})
    write(
        "/etc/fstab", "UUID=f00d / btrfs subvol=/@ 0 0\nUUID=f00d /swap btrfs subvol=/@swap 0 0\n"
    )
    apply("swap", cfg)
    mount = [
        c
        for c in btrfs.calls
        if c[0] in ("mount", "umount") or c[:3] == ["btrfs", "subvolume", "create"]
    ]
    assert [c[0] for c in mount] == ["mount", "btrfs", "umount"]
    assert mount[0][:4] == ["mount", "-o", "subvolid=5", "/dev/mapper/root"]
    assert mount[1][-1].endswith("/@swap")
    unit = engine.path("/etc/systemd/system/swap.mount").read_text()
    assert "What=UUID=f00d\n" in unit and "Options=noatime,subvol=/@swap\n" in unit
    order = [
        c[:3] for c in btrfs.calls if c[0] in ("systemctl", "mkdir", "btrfs") and "is-" not in c[1]
    ]
    assert order[-6:] == [
        ["btrfs", "subvolume", "create"],
        ["systemctl", "daemon-reload"],
        ["mkdir", "-p", "/swap"],
        ["systemctl", "enable", "--now"],
        ["btrfs", "filesystem", "mkswapfile"],
        ["systemctl", "enable", "--now"],
    ]
    assert engine.notices[0].startswith("/etc/fstab still has a line for /swap")
    capsys.readouterr()

    running(btrfs, "swap.mount", "swap-swapfile.swap")
    write("/swap/swapfile", "")
    btrfs.calls.clear()
    apply("swap", cfg)
    assert capsys.readouterr().out == ""
    assert not [c for c in btrfs.calls if c[0] not in ("findmnt", "systemctl")]


def test_swap_needs_a_size_and_btrfs(btrfs):
    with pytest.raises(engine.Failed, match="features.swap.size is empty"):
        apply("swap")
    btrfs.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, "ext4\n")
    with pytest.raises(engine.Failed, match="^/ is ext4"):
        apply("swap", defaults(swap={"size": "8g"}))


def test_swap_keeps_an_existing_subvolume(btrfs):
    btrfs.answers[("btrfs", "subvolume", "list", "/")] = (0, "ID 256 path @\nID 257 path @swap\n")
    apply("swap", defaults(swap={"size": "8g"}))
    assert not [c for c in btrfs.calls if c[0] == "mount"]
