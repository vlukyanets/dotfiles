import grp
import json
import os
import pwd
import subprocess
from pathlib import Path
from urllib.parse import urlencode

import pytest
from conftest import Fake

from dotfiles import engine, retry
from dotfiles.engine import Failed
from dotfiles.errors import ConfigError
from dotfiles.platforms import discovery
from dotfiles.platforms.arch import ArchLinuxOs
from dotfiles.platforms.debian import DebianOs
from dotfiles.platforms.discovery import detect


@pytest.fixture
def system(monkeypatch) -> Fake:
    fake = Fake({"systemctl", "sysctl", "gsettings", "usermod", "pacman"}).install(monkeypatch)
    monkeypatch.setenv("SUDO_CMD", "")
    return fake


@pytest.fixture
def arch() -> ArchLinuxOs:
    return ArchLinuxOs(engine.current())


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
    conf = engine.current().files.path("/") / "etc/sysctl.d/99-dotfiles.conf"
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
    assert "log out and back in" in out.err and engine.current().report.notices
    groups["docker"] = grp.struct_group(("docker", "x", 970, [me]))
    assert arch.ensure_group_member("docker") is False
    with pytest.raises(Failed, match="^group nope does not exist$"):
        arch.ensure_group_member("nope")


def test_arch_missing(system, arch):
    system.answers[("pacman", "-T", "bash", "docker")] = (127, "docker\n")
    assert arch.manager.missing(["bash", "docker"]) == ["docker"]
    assert arch.manager.missing([]) == []
    system.answers[("pacman", "-T", "bash")] = (0, "")
    assert arch.manager.missing(["bash"]) == []


def si(*names: str) -> str:
    """pacman -Si output for NAMES."""
    return "\n".join(f"Repository      : extra\nName            : {n}\n" for n in names)


def test_arch_install_is_one_transaction_as_root(system, arch, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo")
    system.programs.add("sudo")
    system.answers[("pacman", "-Si", "docker", "tmux")] = (0, si("docker", "tmux"))
    arch.manager.install(["docker", "tmux"])
    assert system.calls[-2:] == [
        ["sudo", "pacman", "-Sw", "--needed", "--noconfirm", "docker", "tmux"],
        ["sudo", "pacman", "-S", "--needed", "--noconfirm", "docker", "tmux"],
    ]


def test_arch_install_removes_what_it_replaces(system, arch, capsys):
    system.answers[("pacman", "-Qq", "jack2")] = (0, "jack2\n")
    system.answers[("pacman", "-Qq", "rust")] = (0, "rustup\n")  # only provides rust
    system.answers[("pacman", "-Si", "pipewire-jack")] = (0, si("pipewire-jack"))
    arch.manager.install(["pipewire-jack"], ["jack2", "rust"])
    assert [c for c in system.calls if c[1] != "-Qq" and c[1] != "-Si"] == [
        ["pacman", "-Rdd", "--noconfirm", "jack2"],
        ["pacman", "-Sw", "--needed", "--noconfirm", "pipewire-jack"],
        ["pacman", "-S", "--needed", "--noconfirm", "pipewire-jack"],
    ]
    assert capsys.readouterr().out == "-> removed jack2, its replacement follows\n"


def test_arch_install_leaves_what_is_not_in_the_repositories_for_build(system, arch):
    system.answers[("pacman", "-Si", "tmux", "clock-rs-git")] = (0, si("tmux"))
    assert arch.manager.install(["tmux", "clock-rs-git"]) == ["clock-rs-git"]
    assert system.calls[1:] == [
        ["pacman", "-Sw", "--needed", "--noconfirm", "tmux"],
        ["pacman", "-S", "--needed", "--noconfirm", "tmux"],
    ]


def aur_info(*infos: dict) -> tuple[int, str]:
    """curl's answer: the AUR RPC's results for INFOS."""
    return 0, json.dumps({"results": [{"PackageBase": i["Name"], **i} for i in infos]})


def rpc(*names: str) -> tuple[str, ...]:
    return (
        "curl",
        "-fsSL",
        f"https://aur.archlinux.org/rpc/v5/info?{urlencode([('arg[]', n) for n in names])}",
    )


@pytest.fixture
def aur(system, monkeypatch) -> Fake:
    """makepkg that builds NAME-1-1-x86_64.pkg.tar.zst in its directory, pacman -Qqp that reads it."""
    system.programs |= {"curl", "git", "makepkg"}

    def execute(argv, check=False, **kwargs):
        if argv[:2] == ["git", "clone"]:
            Path(argv[-1]).mkdir(parents=True)
        if argv[0] == "makepkg":
            pkg = kwargs["cwd"] / f"{kwargs['cwd'].name}-1-1-x86_64.pkg.tar.zst"
            if argv[1] == "--noconfirm":
                pkg.touch()
            else:  # --packagelist
                system.answers[tuple(argv)] = (0, str(pkg))
                system.answers[("pacman", "-Qqp", str(pkg))] = (0, kwargs["cwd"].name)
        return system(argv, check, **kwargs)

    monkeypatch.setattr(engine.current().shell, "execute", execute)
    monkeypatch.setenv("SUDO_CMD", "sudo")
    system.programs.add("sudo")
    return system


def test_aur_builds_as_the_user_and_installs_as_root_dependencies_first(aur, arch, capsys):
    app = {"Name": "app", "Depends": ["libfoo>=1", "glibc"], "MakeDepends": ["cargo"]}
    aur.answers[rpc("app")] = aur_info(app)
    aur.answers[rpc("libfoo")] = aur_info({"Name": "libfoo"})
    aur.answers[("pacman", "-T", "libfoo>=1", "glibc", "cargo")] = (127, "libfoo>=1\ncargo\n")
    aur.answers[("pacman", "-Sp", "--print-format", "%n", "libfoo")] = (1, "")
    aur.answers[("pacman", "-Sp", "--print-format", "%n", "cargo")] = (0, "rustup")
    arch.manager.build(["app"])
    cache = Path(os.environ["XDG_CACHE_HOME"]) / "dotfiles/aur"
    mutations = [
        c for c in aur.calls if c[0] in ("git", "sudo") or c[:2] == ["makepkg", "--noconfirm"]
    ]
    assert mutations == [
        ["sudo", "pacman", "-Sw", "--needed", "--noconfirm", "cargo"],
        ["sudo", "pacman", "-S", "--needed", "--noconfirm", "--asdeps", "cargo"],
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "https://aur.archlinux.org/libfoo.git",
            str(cache / "libfoo"),
        ],
        # As the user: no sudo, and no -s, which would call it.
        ["makepkg", "--noconfirm", "--force", "--cleanbuild", "--clean", "--nocheck"],
        [
            "sudo",
            "pacman",
            "-U",
            "--noconfirm",
            "--asdeps",
            str(cache / "libfoo/libfoo-1-1-x86_64.pkg.tar.zst"),
        ],
        [
            "git",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "https://aur.archlinux.org/app.git",
            str(cache / "app"),
        ],
        ["makepkg", "--noconfirm", "--force", "--cleanbuild", "--clean", "--nocheck"],
        [
            "sudo",
            "pacman",
            "-U",
            "--noconfirm",
            str(cache / "app/app-1-1-x86_64.pkg.tar.zst"),
        ],
    ]
    assert capsys.readouterr().out == "-> libfoo built from the AUR\n-> app built from the AUR\n"


def test_aur_builds_again_from_what_it_has(aur, arch):
    src = Path(os.environ["XDG_CACHE_HOME"]) / "dotfiles/aur/app"
    (src / ".git").mkdir(parents=True)
    (src / "app-0.9.tar.gz").touch()  # a source makepkg already has
    (src / "app-0.9-1-x86_64.pkg.tar.zst").touch()  # an earlier build
    aur.answers[rpc("app")] = aur_info({"Name": "app"})
    arch.manager.build(["app"])
    assert [c[:2] for c in aur.calls if c[0] == "git"] == [["git", "fetch"], ["git", "reset"]]
    assert sorted(p.name for p in src.iterdir()) == [
        ".git",
        "app-0.9.tar.gz",
        "app-1-1-x86_64.pkg.tar.zst",
    ]


def test_aur_fails_on_what_it_does_not_have(aur, arch):
    aur.answers[rpc("nope")] = aur_info()
    with pytest.raises(Failed, match="^not in the repositories nor the AUR: nope$"):
        arch.manager.build(["nope"])


def test_aur_refuses_to_build_as_root(aur, arch, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(Failed, match="makepkg refuses root"):
        arch.manager.build(["app"])
    assert aur.calls == []


def test_arch_install_failure_names_the_stale_database(system, arch, monkeypatch):
    monkeypatch.setattr(retry, "sleep", lambda seconds: None)
    system.answers[("pacman", "-Si", "tmux")] = (0, si("tmux"))
    system.answers[("pacman", "-Sw", "--needed", "--noconfirm", "tmux")] = (1, "")
    with pytest.raises(Failed, match="run pacman -Syu and apply again"):
        arch.manager.install(["tmux"])
    assert system.calls.count(["pacman", "-Sw", "--needed", "--noconfirm", "tmux"]) == 3
    assert ["pacman", "-S", "--needed", "--noconfirm", "tmux"] not in system.calls


def test_arch_install_is_not_retried(system, arch, monkeypatch):
    monkeypatch.setattr(retry, "sleep", lambda seconds: pytest.fail("retried"))
    system.answers[("pacman", "-Si", "tmux")] = (0, si("tmux"))
    system.answers[("pacman", "-S", "--needed", "--noconfirm", "tmux")] = (1, "")  # a conflict
    with pytest.raises(subprocess.CalledProcessError):
        arch.manager.install(["tmux"])


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
    assert arch.manager.depends(["docker"]) == {
        "docker": {"bridge-utils", "containerd", "iptables", "libseccomp", "runc", "glibc"}
    }
    assert [c[:2] for c in system.calls].count(["pacman", "-Si"]) == 3
    calls = len(system.calls)
    assert arch.manager.depends(["containerd"]) == {"containerd": {"runc"}}
    assert len(system.calls) == calls  # cached for the apply


def test_arch_provides(system, arch):
    info = "Name : bash\nProvides : sh=5.2\n\nName : zsh\nProvides : None\n"
    system.answers[("pacman", "-Si", "bash", "zsh", "mine")] = (1, info)
    system.answers[("pacman", "-Qi", "mine")] = (0, "Name : mine\nProvides : java-runtime\n")
    assert arch.manager.provides(["bash", "zsh", "mine"]) == {
        "bash": {"sh"},
        "zsh": set(),
        "mine": {"java-runtime"},
    }


def test_detect(monkeypatch):
    def release(**fields):
        monkeypatch.setattr(discovery.platform, "freedesktop_os_release", lambda: fields)

    release(ID="arch")
    assert type(detect(engine.current())) is ArchLinuxOs
    release(ID="cachyos", ID_LIKE="arch")
    assert type(detect(engine.current())) is ArchLinuxOs
    release(ID="fedora")
    with pytest.raises(ConfigError, match="^no platform for fedora$"):
        detect(engine.current())
    release(ID="debian")
    assert type(detect(engine.current())) is DebianOs
    release(ID="linuxmint", ID_LIKE="ubuntu debian")
    assert type(detect(engine.current())) is DebianOs
    release(ID="rocky", ID_LIKE="rhel centos fedora")
    with pytest.raises(ConfigError, match="^no platform for rocky or rhel or centos or fedora$"):
        detect(engine.current())


@pytest.fixture
def debian(monkeypatch) -> DebianOs:
    return DebianOs(engine.current())


APT = ["apt-get", "-q", "-y"]
DPKG = ["dpkg-query", "-W", "-f=${Package} ${db:Status-Status}\n"]


def candidate(system, name: str, version: str = "1.0-1") -> None:
    system.answers[("apt-cache", "policy", name)] = (0, f"{name}:\n  Candidate: {version}\n")


def test_debian_missing(fake, debian):
    fake.answers[(*DPKG, "zsh", "curl", "vim", "nope")] = (
        1,
        "zsh not-installed\ncurl installed\nvim config-files\n",
    )
    assert debian.manager.missing(["zsh", "curl", "vim", "nope"]) == ["zsh", "vim", "nope"]
    assert debian.manager.missing([]) == []


def test_debian_install_updates_then_installs_in_one_transaction_as_root(fake, debian, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo")
    candidate(fake, "zsh")
    candidate(fake, "tmux")
    debian.manager.install(["zsh", "tmux"])
    assert [c for c in fake.calls if c[0] == "sudo"] == [
        ["sudo", *APT, "update"],
        ["sudo", *APT, "install", "--download-only", "zsh", "tmux"],
        ["sudo", *APT, "install", "zsh", "tmux"],
    ]


def test_debian_install_leaves_what_the_repositories_lack(fake, debian, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "")
    candidate(fake, "zsh")
    candidate(fake, "zsh-completions", "(none)")
    assert debian.manager.install(["zsh", "zsh-completions", "nope"]) == ["zsh-completions", "nope"]
    assert fake.calls[-1] == [*APT, "install", "zsh"]


def test_debian_install_removes_what_it_replaces(fake, debian, monkeypatch, capsys):
    monkeypatch.setenv("SUDO_CMD", "")
    fake.answers[(*DPKG, "rustc")] = (0, "rustc installed\n")
    fake.answers[(*DPKG, "cargo")] = (1, "")
    debian.manager.install([], ["rustc", "cargo"])
    assert [c for c in fake.calls if c[0] == "apt-get"] == [
        [*APT, "update"],
        [*APT, "remove", "rustc"],
    ]
    assert capsys.readouterr().out == "-> removed rustc, its replacement follows\n"


def test_debian_depends_walks_the_graph(fake, debian):
    zsh = "zsh\n  Depends: zsh-common\n  PreDepends: libc6\n |Depends: mawk\n  Depends: <awk>\n"
    fake.answers[("apt-cache", "depends", "-i", "zsh", "nope")] = (0, zsh)
    fake.answers[("apt-cache", "depends", "-i", "zsh")] = (0, zsh)
    fake.answers[("apt-cache", "depends", "-i", "awk", "libc6", "mawk", "zsh-common")] = (
        0,
        "libc6\n  Depends: libgcc-s1\nzsh-common\n",
    )
    fake.answers[("apt-cache", "depends", "-i", "libgcc-s1")] = (0, "libgcc-s1\n")
    assert debian.manager.direct(["zsh", "nope"]) == {
        "zsh": {"zsh-common", "libc6", "mawk", "awk"},
        "nope": set(),
    }
    assert debian.manager.depends(["zsh"])["zsh"] >= {"libgcc-s1", "zsh-common"}
