import grp
import os
import pwd
import subprocess
import tomllib
from pathlib import Path

import pytest
from conftest import AsRoot, Fake

from dotfiles import engine, platforms
from dotfiles.config import ROOT, ConfigError
from dotfiles.engine import Failed
from dotfiles.platforms import detect
from dotfiles.platforms.arch import Arch


@pytest.fixture
def system(monkeypatch) -> Fake:
    """systemctl, sysctl, gsettings, usermod and pacman faked; sudo prefix
    off so the calls read as the commands themselves."""
    fake = Fake({"systemctl", "sysctl", "gsettings", "usermod", "pacman"})
    monkeypatch.setattr(engine, "_run", fake)
    monkeypatch.setenv("SUDO_CMD", "")
    return fake


@pytest.fixture
def arch() -> Arch:
    return Arch({})


@pytest.mark.parametrize(
    ("enabled", "active", "call"),
    [
        ("disabled", "inactive", ["enable", "--now"]),
        ("", "", ["enable", "--now"]),  # not installed yet
        ("enabled", "failed", ["start"]),
        ("static", "inactive", ["start"]),
    ],
)
def test_ensure_service(system, arch, capsys, enabled, active, call):
    for user, scope in ((False, []), (True, ["--user"])):
        system.calls.clear()
        system.answers = {
            ("systemctl", *scope, "is-enabled", "x.timer"): (1, enabled + "\n"),
            ("systemctl", *scope, "is-active", "x.timer"): (3, active + "\n"),
        }
        assert arch.ensure_service("x.timer", user=user) is True
        assert system.calls[-1] == ["systemctl", *scope, *call, "x.timer"]
        assert (
            capsys.readouterr().out == f"-> x.timer enabled and started (was {enabled}/{active})\n"
        )
        system.calls.clear()
        system.answers = {
            ("systemctl", *scope, "is-enabled", "x.timer"): (0, "enabled\n"),
            ("systemctl", *scope, "is-active", "x.timer"): (0, "active\n"),
        }
        assert arch.ensure_service("x.timer", user=user) is False
        assert all(c[-2] in ("is-enabled", "is-active") for c in system.calls)


def test_ensure_sysctl(system, arch, capsys):
    system.answers[("sysctl", "-n", "vm.swappiness")] = (0, "60\n")
    assert arch.ensure_sysctl("vm.swappiness", 10) is True
    assert ["sysctl", "-qw", "vm.swappiness=10"] in system.calls
    conf = engine.SYSROOT / "etc/sysctl.d/99-dotfiles.conf"
    assert conf.read_text() == "vm.swappiness = 10\n"
    system.answers[("sysctl", "-n", "vm.swappiness")] = (0, "10\n")
    system.calls.clear()
    assert arch.ensure_sysctl("vm.swappiness", 10) is False
    assert system.calls == [["sysctl", "-n", "vm.swappiness"]]
    assert capsys.readouterr().out == (
        "-> /etc/sysctl.d/99-dotfiles.conf (missing)\n-> sysctl vm.swappiness = 10\n"
    )


def test_ensure_gsetting(system, arch, capsys, monkeypatch):
    get = ("gsettings", "get", "org.gnome.desktop.interface", "color-scheme")
    system.answers[get] = (0, "'default'\n")
    assert arch.ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
    assert system.calls[-1] == [
        "gsettings",
        "set",
        "org.gnome.desktop.interface",
        "color-scheme",
        "'prefer-dark'",
    ]
    system.answers[get] = (0, "'prefer-dark'\n")
    assert not arch.ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
    system.programs.discard("gsettings")
    monkeypatch.setenv("PATH", "")  # no gsettings installed
    assert not arch.ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'x'")
    assert capsys.readouterr().out == (
        "-> gsettings org.gnome.desktop.interface color-scheme = 'prefer-dark'\n"
    )


def test_ensure_group_member(system, arch, capsys, monkeypatch):
    me = pwd.getpwuid(engine.os.geteuid()).pw_name
    groups = {"docker": grp.struct_group(("docker", "x", 970, []))}

    def getgrnam(name):
        return groups[name]

    monkeypatch.setattr(engine.grp, "getgrnam", getgrnam)
    assert arch.ensure_group_member("docker") is True
    assert system.calls == [["usermod", "-aG", "docker", me]]
    out = capsys.readouterr()
    assert out.out == f"-> added {me} to group docker\n"
    assert "log out and back in" in out.err and engine.notices
    groups["docker"] = grp.struct_group(("docker", "x", 970, [me]))
    assert arch.ensure_group_member("docker") is False
    with pytest.raises(Failed, match="^group nope does not exist$"):
        arch.ensure_group_member("nope")
    # A dry run installs nothing, so the package that brings the group has not yet.
    monkeypatch.setattr(engine, "DRY_RUN", True)
    capsys.readouterr()
    assert arch.ensure_group_member("nope") is True
    assert capsys.readouterr().out == f"-> added {me} to group nope\n"


def test_arch_missing(system, arch):
    system.answers[("pacman", "-T", "bash", "docker")] = (127, "docker\n")
    assert arch.missing(["bash", "docker"]) == ["docker"]
    assert arch.missing([]) == []
    system.answers[("pacman", "-T", "bash")] = (0, "")
    assert arch.missing(["bash"]) == []


def si(*names: str) -> str:
    """pacman -Si output for NAMES."""
    return "\n".join(f"Repository      : extra\nName            : {n}\n" for n in names)


def test_arch_install_is_one_transaction_as_root(system, arch, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo")
    system.programs.add("sudo")
    system.answers[("pacman", "-Si", "docker", "tmux")] = (0, si("docker", "tmux"))
    arch.install(["docker", "tmux"])
    assert system.calls[-1] == ["sudo", "pacman", "-S", "--needed", "--noconfirm", "docker", "tmux"]


def test_arch_install_removes_what_it_replaces(system, arch, capsys):
    system.answers[("pacman", "-Qq", "jack2")] = (0, "jack2\n")
    system.answers[("pacman", "-Qq", "rust")] = (0, "rustup\n")  # only provides rust
    system.answers[("pacman", "-Si", "pipewire-jack")] = (0, si("pipewire-jack"))
    arch.install(["pipewire-jack"], ["jack2", "rust"])
    assert [c for c in system.calls if c[1] != "-Qq" and c[1] != "-Si"] == [
        ["pacman", "-Rdd", "--noconfirm", "jack2"],
        ["pacman", "-S", "--needed", "--noconfirm", "pipewire-jack"],
    ]
    assert capsys.readouterr().out == "-> removed jack2, its replacement follows\n"


def test_arch_install_takes_the_rest_from_the_aur(system, monkeypatch):
    system.programs.add("paru")
    system.answers[("pacman", "-Si", "tmux", "clock-rs-git")] = (0, si("tmux"))
    system.answers[("paru", "--version")] = (0, "paru v2.1.0 - libalpm v16.0.1\n")
    Arch(config(aur={})).install(["tmux", "clock-rs-git"])
    assert [c for c in system.calls if c[1] in ("-S", "--version")] == [
        ["pacman", "-S", "--needed", "--noconfirm", "tmux"],
        ["paru", "--version"],
        ["paru", "-S", "--needed", "--noconfirm", "clock-rs-git"],
    ]
    # paru's own sudo is SUDO_CMD, snap-pac's skip kept.
    monkeypatch.setenv("SUDO_CMD", "false")
    monkeypatch.setenv("SNAP_PAC_SKIP", "y")
    Arch(config(aur={})).install(["clock-rs-git"])
    assert system.calls[-1] == [
        "paru",
        "--sudo",
        "false",
        "--sudoflags",
        "--preserve-env=SNAP_PAC_SKIP",
        *["-S", "--needed", "--noconfirm", "clock-rs-git"],
    ]


def test_arch_install_without_the_aur_fails_after_the_repositories(system):
    system.answers[("pacman", "-Si", "tmux", "clock-rs-git")] = (0, si("tmux"))
    with pytest.raises(Failed, match="not in the repositories: clock-rs-git — enable features.aur"):
        Arch(config()).install(["tmux", "clock-rs-git"])
    assert system.calls[-1] == ["pacman", "-S", "--needed", "--noconfirm", "tmux"]


def test_arch_install_failure_names_the_stale_database(system, monkeypatch):
    monkeypatch.setattr(engine, "sleep", lambda seconds: None)
    system.answers[("pacman", "-Si", "tmux")] = (0, si("tmux"))
    system.answers[("pacman", "-S", "--needed", "--noconfirm", "tmux")] = (1, "")
    with pytest.raises(Failed, match="run pacman -Syu and apply again"):
        Arch(config()).install(["tmux"])
    assert system.calls.count(["pacman", "-S", "--needed", "--noconfirm", "tmux"]) == 3


SI = """Repository      : extra
Name            : docker
Version         : 1:28.0-1
Depends On      : bridge-utils  containerd>=1.7  iptables  libseccomp
Optional Deps   : btrfs-progs: btrfs backend support
                  pigz: for faster compression

Repository      : extra
Name            : containerd
Depends On      : runc

Repository      : extra
Name            : bridge-utils
Depends On      : None
"""


def test_arch_depends_walks_the_graph(system, arch):
    system.answers[("pacman", "-Si", "docker")] = (0, SI.split("\n\n")[0])
    system.answers[("pacman", "-Si", "bridge-utils", "containerd", "iptables", "libseccomp")] = (
        1,
        "\n\n".join(SI.split("\n\n")[1:]),
    )
    local = "Name : iptables\nDepends On : glibc\n\nName : libseccomp\nDepends On : None\n"
    system.answers[("pacman", "-Qi", "iptables", "libseccomp")] = (0, local)
    assert arch.depends(["docker"]) == {
        "docker": {"bridge-utils", "containerd", "iptables", "libseccomp", "runc", "glibc"}
    }
    # Level by level: docker; its four; then runc and glibc (the sync
    # database knows neither here, so both are asked locally too).
    assert [c[:2] for c in system.calls].count(["pacman", "-Si"]) == 3
    calls = len(system.calls)
    assert arch.depends(["containerd"]) == {"containerd": {"runc"}}
    assert len(system.calls) == calls  # cached for the apply


def test_detect(monkeypatch):
    def release(**fields):
        monkeypatch.setattr(platforms.platform, "freedesktop_os_release", lambda: fields)

    release(ID="arch")
    assert type(detect({})) is Arch
    release(ID="cachyos", ID_LIKE="arch")
    assert detect({"x": 1}).cfg == {"x": 1}
    release(ID="fedora")
    with pytest.raises(ConfigError, match="^no platform for fedora$"):
        detect({})
    release(ID="linuxmint", ID_LIKE="ubuntu debian")
    with pytest.raises(ConfigError, match="^no platform for linuxmint or ubuntu or debian$"):
        detect({})


@pytest.fixture
def root(machine) -> AsRoot:
    return machine


def config(**features) -> dict:
    """Every setup part off but FEATURES, with the defaults' settings."""
    defaults = tomllib.loads((ROOT / "dotfiles/defaults.toml").read_text())
    for name, settings in features.items():
        defaults["features"][name].update(enabled=True, **settings)
    return defaults


def test_setup_off_runs_nothing(root, capsys):
    Arch(config()).setup()
    assert root.calls == []
    assert capsys.readouterr().out == ""


def test_setup_pacman(root, capsys):
    conf = engine.SYSROOT / "etc/pacman.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[options]\nHoldPkg = pacman\n\n[core]\nInclude = /etc/pacman.d/mirrorlist\n")
    arch = Arch(config(pacman={"parallel_downloads": 2}))
    arch.setup()
    assert conf.read_text() == (
        "[options]\nHoldPkg = pacman\n\nInclude = /etc/pacman.conf.d/options.conf\n"
        "[core]\nInclude = /etc/pacman.d/mirrorlist\n"
    )
    options = engine.SYSROOT / "etc/pacman.conf.d/options.conf"
    assert options.read_text() == "ParallelDownloads = 2\n"
    capsys.readouterr()
    arch.setup()
    assert capsys.readouterr().out == ""

    arch = Arch(config(pacman={"multilib": True}))
    arch.setup()
    assert conf.read_text().endswith("\nInclude = /etc/pacman.conf.d/multilib.conf\n")
    multilib = engine.SYSROOT / "etc/pacman.conf.d/multilib.conf"
    assert multilib.read_text() == "[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"
    assert root.calls[-1] == ["pacman", "-Syu", "--noconfirm"]
    assert capsys.readouterr().out.endswith("-> multilib database synced (pacman -Syu)\n")
    # Until the database exists, every apply syncs again; then nothing.
    db = engine.SYSROOT / "var/lib/pacman/sync/multilib.db"
    db.parent.mkdir(parents=True)
    db.touch()
    root.calls.clear()
    arch.setup()
    assert capsys.readouterr().out == ""
    assert not any(call[0] == "pacman" for call in root.calls)


def test_setup_leaves_a_multilib_of_pacman_conf_alone(root):
    conf = engine.SYSROOT / "etc/pacman.conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("[options]\n[core]\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n")
    Arch(config(pacman={"multilib": True})).setup()
    assert not (engine.SYSROOT / "etc/pacman.conf.d/multilib.conf").exists()
    assert "multilib.conf" not in conf.read_text()
    assert not any(call[0] == "pacman" for call in root.calls)


@pytest.mark.parametrize(
    ("jobs", "options", "makeflags", "extra"),
    [
        ("20%", ["ccache", "!debug"], "-j3", "OPTIONS+=(ccache !debug)\n"),
        ("1%", [], "-j1", ""),  # never below one job
        ("$(nproc)", [], "-j$(nproc)", ""),  # evaluated by makepkg
    ],
)
def test_setup_makepkg(root, monkeypatch, jobs, options, makeflags, extra):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    cfg = config(makepkg={"jobs": jobs, "options": options})
    cfg["git"].update(name="A B", email="a@b")
    Arch(cfg).setup()
    conf = engine.SYSROOT / "etc/makepkg.conf.d/dotfiles.conf"
    assert conf.read_text() == f'MAKEFLAGS="{makeflags}"\n{extra}PACKAGER="A B <a@b>"\n'


def test_setup_reflector(root, capsys):
    arch = Arch(config(reflector={"country": ["Ukraine", "Poland"]}))
    root.answers[("pacman", "-T", "reflector")] = (127, "reflector\n")
    root.answers[("pacman", "-Si", "reflector")] = (0, si("reflector"))
    arch.setup()
    conf = engine.SYSROOT / "etc/xdg/reflector/reflector.conf"
    assert conf.read_text() == (
        "--save /etc/pacman.d/mirrorlist\n--country Ukraine,Poland\n--protocol https\n"
        "--latest 20\n--sort rate\n--age 12\n--completion-percent 100\n--download-timeout 5\n"
    )
    override = engine.SYSROOT / "etc/systemd/system/reflector.timer.d/override.conf"
    assert override.read_text() == (
        "[Timer]\nOnCalendar=\nOnCalendar=weekly\nOnBootSec=\nOnBootSec=15min\n"
    )
    commands = [call for call in root.calls if call[0] != "install"]
    assert commands[commands.index(["pacman", "-S", "--needed", "--noconfirm", "reflector"]) :] == [
        ["pacman", "-S", "--needed", "--noconfirm", "reflector"],
        ["systemctl", "daemon-reload"],
        ["systemctl", "is-enabled", "reflector.timer"],
        ["systemctl", "is-active", "reflector.timer"],
        ["systemctl", "enable", "--now", "reflector.timer"],
        ["systemctl", "start", "reflector.service"],
    ]
    out = capsys.readouterr().out
    assert out.startswith("-> packages: reflector (missing)\n")
    assert out.endswith("-> mirrorlist refreshed\n")

    # In place: nothing started, nothing printed.
    root.answers = {
        ("systemctl", "is-enabled", "reflector.timer"): (0, "enabled\n"),
        ("systemctl", "is-active", "reflector.timer"): (0, "active\n"),
    }
    root.calls.clear()
    arch.setup()
    assert capsys.readouterr().out == ""
    assert ["systemctl", "start", "reflector.service"] not in root.calls
    assert ["systemctl", "daemon-reload"] not in root.calls

    # A new schedule: daemon-reload and a refresh; a failed refresh is a notice.
    arch.cfg["features"]["reflector"]["on_calendar"] = "daily"
    root.answers[("systemctl", "start", "reflector.service")] = (1, "")
    arch.setup()
    assert ["systemctl", "daemon-reload"] in root.calls
    assert engine.notices[0].startswith("refreshing the mirrorlist failed (network?)")


SRCINFO = """pkgbase = paru
\tpkgver = 2.1.0
\tmakedepends = cargo
\tdepends = git
\tdepends = pacman
\tdepends = libalpm.so>=16
pkgname = paru
"""


class Clone(Fake):
    """git clone leaves a checkout with SRCINFO; makepkg --packagelist names
    a file it creates."""

    def __call__(self, argv, check=False, **kwargs):
        if argv[:2] == ["git", "clone"]:
            Path(argv[-1]).mkdir()
            (Path(argv[-1]) / ".SRCINFO").write_text(SRCINFO)
        if argv[:2] == ["makepkg", "--packagelist"]:
            built = Path(kwargs["cwd"]) / "paru-2.1.0-1-x86_64.pkg.tar.zst"
            built.touch()
            return subprocess.CompletedProcess(argv, 0, f"{built}\n{built}.debug\n", "")
        return super().__call__(argv, check, **kwargs)


def test_ensure_paru(monkeypatch, capsys):
    fake = Clone()
    monkeypatch.setattr(engine, "_run", fake)
    monkeypatch.setenv("SUDO_CMD", "")
    fake.answers[("paru", "--version")] = (0, "paru v2.1.0 - libalpm v16.0.1\n")
    arch = Arch(config(aur={}))
    assert arch.ensure_paru() is False
    assert fake.calls == [["paru", "--version"]]

    # A paru that does not run is built: deps first, as root through pacman.
    fake.answers = {
        ("paru", "--version"): (127, ""),
        ("pacman", "-T", "base-devel", "git"): (127, "base-devel\n"),
        ("pacman", "-T", "cargo", "git", "libalpm.so", "pacman"): (127, "cargo\n"),
        ("rustup", "default"): (1, ""),  # rustup without a toolchain
    }
    assert arch.ensure_paru() is True
    mutations = [c for c in fake.calls if c[:2] not in (["pacman", "-T"], ["paru", "--version"])]
    assert mutations[0] == ["pacman", "-S", "--needed", "--noconfirm", "base-devel"]
    assert mutations[1][:5] == ["git", "clone", "--quiet", "--depth", "1"]
    assert mutations[2:6] == [
        ["pacman", "-S", "--needed", "--noconfirm", "--asdeps", "cargo"],
        ["rustup", "default"],
        ["rustup", "default", "stable"],
        ["makepkg", "--noconfirm"],
    ]
    assert mutations[-1][:3] == ["pacman", "-U", "--noconfirm"]
    assert mutations[-1][3].endswith("/paru-2.1.0-1-x86_64.pkg.tar.zst")
    assert len(mutations[-1]) == 4  # the .debug file was not built
    assert capsys.readouterr().out == "-> paru built from the AUR\n"


def test_ensure_paru_dry_run(system, monkeypatch, capsys):
    monkeypatch.setattr(engine, "DRY_RUN", True)
    system.programs.add("paru")
    assert Arch(config(aur={})).ensure_paru() is True
    assert system.calls == [["paru", "--version"]]
    assert capsys.readouterr().out == "-> paru built from the AUR\n"


def test_watching_runs_before_each_package_change(system, monkeypatch):
    seen = []
    system.answers[("pacman", "-Si", "tmux")] = (0, si("tmux"))
    system.answers[("pacman", "-Qq", "jack2")] = (0, "jack2\n")

    def hook():
        seen.append(len(system.calls))

    arch = Arch(config())
    with platforms.watching(hook):
        arch.install(["tmux"], ["jack2"])
    # Before -Rdd (after the -Qq check) and before -S (after the -Si query).
    assert [system.calls[i][1] for i in seen] == ["-Rdd", "-S"]
    arch.install(["tmux"])  # outside the block: not watched
    assert len(seen) == 2
    monkeypatch.setattr(engine, "DRY_RUN", True)
    with platforms.watching(hook):
        arch.install(["tmux"])  # a dry run changes nothing
    assert len(seen) == 2
