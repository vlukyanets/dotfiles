import subprocess

import pytest

from dotfiles import engine
from dotfiles.engine import (
    Deferred,
    Failed,
    Skip,
    as_root,
    defer,
    die,
    notice,
    os_guard,
    output,
    print_notices,
    retry,
    run,
)


class Fake:
    """Stands in for engine._run: answers from ANSWERS (argv tuple -> (rc,
    stdout)), 0 and "" otherwise, and records every argv in CALLS. With
    PROGRAMS, only those are faked; anything else really runs."""

    def __init__(self, programs=None):
        self.answers: dict[tuple, tuple[int, str]] = {}
        self.calls: list[list[str]] = []
        self.programs = programs

    def __call__(self, argv, check=False, **kwargs):
        if self.programs is not None and argv[0] not in self.programs:
            return subprocess.run(argv, check=check, text=True, **kwargs)
        self.calls.append(argv)
        rc, out = self.answers.get(tuple(argv), (0, ""))
        if rc and check:
            raise subprocess.CalledProcessError(rc, argv)
        return subprocess.CompletedProcess(argv, rc, out, "")


@pytest.fixture
def fake(monkeypatch) -> Fake:
    fake = Fake()
    monkeypatch.setattr(engine, "_run", fake)
    return fake


def test_as_root_prefix(fake, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo -n")
    as_root("true")
    monkeypatch.setenv("DOTFILES_SNAPPER_STATE", "/run/x")
    as_root("true")
    monkeypatch.setenv("SUDO_CMD", "")
    as_root("true")
    monkeypatch.setattr(engine.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_CMD", "sudo")
    as_root("true")
    assert fake.calls == [
        ["sudo", "-n", "true"],
        ["sudo", "-n", "--preserve-env=SNAP_PAC_SKIP,DOTFILES_SNAPPER_STATE", "true"],
        ["true"],
        ["true"],
    ]


def test_sudo_from_conftest_fails():
    with pytest.raises(subprocess.CalledProcessError):
        as_root("true")


def test_mutations_must_succeed(fake):
    fake.answers[("false",)] = (1, "")
    with pytest.raises(subprocess.CalledProcessError):
        run("false")


def test_dry_run_runs_nothing(fake, monkeypatch):
    monkeypatch.setattr(engine, "DRY_RUN", True)
    as_root("rm", "-rf", "/")
    run("touch", "x")
    assert fake.calls == []


def test_output():
    assert output("printf", "a\\nb\\n") == "a\nb"
    assert output("sh", "-c", "echo disabled; exit 1") == "disabled"
    assert output("no-such-command-here") is None


def test_retry(monkeypatch, capsys):
    slept = []
    monkeypatch.setattr(engine, "sleep", slept.append)
    attempts = []

    def flaky(n):
        attempts.append(n)
        if len(attempts) < n:
            raise subprocess.CalledProcessError(1, "x")

    assert retry(flaky, 2) is True
    assert attempts == [2, 2] and slept == [10]
    attempts.clear()
    assert retry(flaky, 9) is False
    assert len(attempts) == 3 and slept == [10, 10, 20]
    assert "warning: 9 failed (attempt 2/3), retrying in 20s" in capsys.readouterr().err


def test_die_defer_os_guard(monkeypatch):
    with pytest.raises(Failed, match="^boom$"):
        die("boom")
    with pytest.raises(Deferred, match="^net$"):
        defer("net")
    release = {"ID": "cachyos", "ID_LIKE": "arch"}
    monkeypatch.setattr(engine.platform, "freedesktop_os_release", lambda: release)
    os_guard("arch")
    os_guard("darwin", "linux")
    with pytest.raises(Skip):
        os_guard("darwin", "debian")


def test_notices_now_and_at_the_end(capsys):
    notice("log out and back in")
    assert capsys.readouterr().err == "warning: log out and back in\n"
    print_notices()
    assert capsys.readouterr().out == "\nNotices from this apply:\n    log out and back in\n"
    print_notices()
    assert capsys.readouterr().out == ""


def me() -> str:
    return engine._owner(engine.SYSROOT.parent)


def test_ensure_file_changes_once(capsys):
    from dotfiles.engine import ensure_file

    real = engine.SYSROOT / "etc/deep/er/f.conf"
    assert ensure_file("/etc/deep/er/f.conf", "a\n", 0o600, owner=me()) is True
    assert ensure_file("/etc/deep/er/f.conf", b"a\n", 0o600, owner=me()) is False
    assert real.read_text() == "a\n" and oct(real.stat().st_mode & 0o777) == "0o600"
    real.write_text("b\n")
    assert ensure_file("/etc/deep/er/f.conf", "a\n", 0o600) is True
    real.chmod(0o644)
    assert ensure_file("/etc/deep/er/f.conf", "a\n", 0o600) is True
    assert ensure_file("/etc/deep/er/f.conf", "a\n", 0o600) is False
    assert capsys.readouterr().out == (
        "-> /etc/deep/er/f.conf (missing)\n"
        "-> /etc/deep/er/f.conf (content differs)\n"
        "-> /etc/deep/er/f.conf (mode 644)\n"
    )


def test_ensure_file_goes_to_root_only_when_needed():
    from dotfiles.engine import ensure_file

    locked = engine.SYSROOT / "etc"
    locked.mkdir(parents=True)
    locked.chmod(0o555)
    try:
        with pytest.raises(subprocess.CalledProcessError) as e:  # SUDO_CMD=false
            ensure_file("/etc/f", "x\n")
        assert e.value.cmd[:2] == ["false", "install"]
        with pytest.raises(subprocess.CalledProcessError):
            ensure_file("/tmp-owned-by-root", "x\n", owner="root:root")
    finally:
        locked.chmod(0o755)


def test_dry_run_reports_and_writes_nothing(monkeypatch, capsys):
    from dotfiles.engine import ensure_file, ensure_line, ensure_symlink

    monkeypatch.setattr(engine, "DRY_RUN", True)
    assert ensure_file("/etc/f", "x\n", owner="root:root") is True
    assert ensure_line("/etc/g", "^x=", "x=1") is True
    assert ensure_symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is True
    assert not engine.SYSROOT.exists()
    assert capsys.readouterr().out == (
        "-> /etc/f (missing)\n-> /etc/g (missing)\n-> /etc/localtime -> /usr/share/zoneinfo/UTC\n"
    )


def test_ensure_line():
    from dotfiles.engine import ensure_line

    conf = engine.SYSROOT / "etc/conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("a=1\n#b=2\nc=3\n#b=9\n")
    conf.chmod(0o600)
    assert ensure_line("/etc/conf", "^#?b=", "b=2") is True
    assert ensure_line("/etc/conf", "^#?b=", "b=2") is False
    assert conf.read_text() == "a=1\nb=2\nc=3\n#b=9\n"
    assert ensure_line("/etc/conf", "^d=", "d=4") is True
    assert ensure_line("/etc/conf", "^d=", "d=4") is False
    assert conf.read_text().endswith("#b=9\nd=4\n")
    assert oct(conf.stat().st_mode & 0o777) == "0o600"
    assert ensure_line("/etc/new", "^x=", "x=1") is True
    assert ensure_line("/etc/new", "^x=", "x=1") is False
    assert (engine.SYSROOT / "etc/new").read_text() == "x=1\n"


def test_ensure_symlink():
    from dotfiles.engine import ensure_symlink

    (engine.SYSROOT / "etc").mkdir(parents=True)
    assert ensure_symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is True
    assert ensure_symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is False
    assert ensure_symlink("/usr/share/zoneinfo/Europe/Berlin", "/etc/localtime") is True
    assert (engine.SYSROOT / "etc/localtime").readlink().as_posix() == (
        "/usr/share/zoneinfo/Europe/Berlin"
    )


@pytest.fixture
def system(monkeypatch) -> Fake:
    """systemctl, sysctl, gsettings and usermod faked; sudo prefix off so the
    calls read as the commands themselves."""
    fake = Fake({"systemctl", "sysctl", "gsettings", "usermod"})
    monkeypatch.setattr(engine, "_run", fake)
    monkeypatch.setenv("SUDO_CMD", "")
    return fake


@pytest.mark.parametrize(
    ("enabled", "active", "call"),
    [
        ("disabled", "inactive", ["enable", "--now"]),
        ("", "", ["enable", "--now"]),  # not installed yet
        ("enabled", "failed", ["start"]),
        ("static", "inactive", ["start"]),
    ],
)
def test_ensure_service(system, capsys, enabled, active, call):
    from dotfiles.engine import ensure_service

    for user, scope in ((False, []), (True, ["--user"])):
        system.calls.clear()
        system.answers = {
            ("systemctl", *scope, "is-enabled", "x.timer"): (1, enabled + "\n"),
            ("systemctl", *scope, "is-active", "x.timer"): (3, active + "\n"),
        }
        assert ensure_service("x.timer", user=user) is True
        assert system.calls[-1] == ["systemctl", *scope, *call, "x.timer"]
        assert (
            capsys.readouterr().out == f"-> x.timer enabled and started (was {enabled}/{active})\n"
        )
        system.calls.clear()
        system.answers = {
            ("systemctl", *scope, "is-enabled", "x.timer"): (0, "enabled\n"),
            ("systemctl", *scope, "is-active", "x.timer"): (0, "active\n"),
        }
        assert ensure_service("x.timer", user=user) is False
        assert all(c[-2] in ("is-enabled", "is-active") for c in system.calls)


def test_ensure_sysctl(system, capsys):
    from dotfiles.engine import ensure_sysctl

    system.answers[("sysctl", "-n", "vm.swappiness")] = (0, "60\n")
    assert ensure_sysctl("vm.swappiness", 10) is True
    assert ["sysctl", "-qw", "vm.swappiness=10"] in system.calls
    conf = engine.SYSROOT / "etc/sysctl.d/99-dotfiles.conf"
    assert conf.read_text() == "vm.swappiness = 10\n"
    system.answers[("sysctl", "-n", "vm.swappiness")] = (0, "10\n")
    system.calls.clear()
    assert ensure_sysctl("vm.swappiness", 10) is False
    assert system.calls == [["sysctl", "-n", "vm.swappiness"]]
    assert capsys.readouterr().out == (
        "-> /etc/sysctl.d/99-dotfiles.conf (missing)\n-> sysctl vm.swappiness = 10\n"
    )


def test_ensure_gsetting(system, capsys, monkeypatch):
    from dotfiles.engine import ensure_gsetting

    get = ("gsettings", "get", "org.gnome.desktop.interface", "color-scheme")
    system.answers[get] = (0, "'default'\n")
    assert ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
    assert system.calls[-1] == [
        "gsettings",
        "set",
        "org.gnome.desktop.interface",
        "color-scheme",
        "'prefer-dark'",
    ]
    system.answers[get] = (0, "'prefer-dark'\n")
    assert not ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'prefer-dark'")
    monkeypatch.setattr(engine, "output", lambda *cmd: None)  # no gsettings installed
    assert not ensure_gsetting("org.gnome.desktop.interface", "color-scheme", "'x'")
    assert capsys.readouterr().out == (
        "-> gsettings org.gnome.desktop.interface color-scheme = 'prefer-dark'\n"
    )


def test_ensure_group_member(system, capsys, monkeypatch):
    import grp
    import pwd

    from dotfiles.engine import ensure_group_member

    me = pwd.getpwuid(engine.os.geteuid()).pw_name
    groups = {"docker": grp.struct_group(("docker", "x", 970, []))}

    def getgrnam(name):
        return groups[name]

    monkeypatch.setattr(engine.grp, "getgrnam", getgrnam)
    assert ensure_group_member("docker") is True
    assert system.calls == [["usermod", "-aG", "docker", me]]
    out = capsys.readouterr()
    assert out.out == f"-> added {me} to group docker\n"
    assert "log out and back in" in out.err and engine.notices
    groups["docker"] = grp.struct_group(("docker", "x", 970, [me]))
    assert ensure_group_member("docker") is False
    with pytest.raises(Failed, match="^group nope does not exist$"):
        ensure_group_member("nope")
