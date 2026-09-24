import grp
import pwd

import pytest
from conftest import Fake

from dotfiles import engine, platforms
from dotfiles.config import ConfigError
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


def test_arch_missing(system, arch):
    system.answers[("pacman", "-T", "bash", "docker")] = (127, "docker\n")
    assert arch.missing(["bash", "docker"]) == ["docker"]
    assert arch.missing([]) == []
    system.answers[("pacman", "-T", "bash")] = (0, "")
    assert arch.missing(["bash"]) == []


def test_arch_install_is_one_transaction_as_root(system, arch, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo")
    system.programs.add("sudo")
    arch.install(["docker", "tmux"])
    assert system.calls == [["sudo", "pacman", "-S", "--needed", "--noconfirm", "docker", "tmux"]]


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
