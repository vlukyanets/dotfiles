import subprocess

import pytest

from dotfiles import engine
from dotfiles.engine import (
    Deferred,
    Failed,
    RetryPolicy,
    as_root,
    defer,
    die,
    notice,
    output,
    print_notices,
    retrying,
    run,
)


def test_as_root_prefix(fake, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo -n")
    run("true")
    with as_root():
        run("true")
        with as_root():
            run("true")
        run("true", cwd="/")
        output("check")  # checks never get root
    run("true")
    monkeypatch.setenv("SNAP_PAC_SKIP", "y")
    with as_root():
        run("true")
    monkeypatch.setenv("SUDO_CMD", "")
    with as_root():
        run("true")
    monkeypatch.setattr(engine.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_CMD", "sudo")
    with as_root():
        run("true")
    assert fake.calls == [
        ["true"],
        ["sudo", "-n", "true"],
        ["sudo", "-n", "true"],
        ["sudo", "-n", "true"],
        ["check"],
        ["true"],
        ["sudo", "-n", "--preserve-env=SNAP_PAC_SKIP", "true"],
        ["true"],
        ["true"],
    ]


def test_sudo_from_conftest_fails():
    with pytest.raises(subprocess.CalledProcessError), as_root():
        run("true")


def test_mutations_must_succeed(fake):
    fake.answers[("false",)] = (1, "")
    with pytest.raises(subprocess.CalledProcessError):
        run("false")


def test_dry_run_runs_nothing(fake, monkeypatch):
    monkeypatch.setattr(engine, "DRY_RUN", True)
    with as_root():
        run("rm", "-rf", "/")
    run("touch", "x")
    assert fake.calls == []


def test_output():
    assert output("printf", "a\\nb\\n") == "a\nb"
    assert output("sh", "-c", "echo disabled; exit 1") == "disabled"
    assert output("no-such-command-here") is None


def test_retry_policy_waits():
    assert [RetryPolicy().wait(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 60]
    assert RetryPolicy(delay=1, backoff=3, max_delay=5).wait(3) == 5


def test_retrying_repeats_the_whole_block(fake, monkeypatch, capsys):
    slept = []
    monkeypatch.setattr(engine, "sleep", slept.append)
    fake.answers[("git", "clone", "u")] = (1, "")
    passes = []
    with pytest.raises(subprocess.CalledProcessError):
        for attempt in retrying():
            with attempt:
                passes.append("mktemp")
                run("git", "clone", "u")
    assert passes == ["mktemp"] * 3 and slept == [10, 20]
    assert capsys.readouterr().err == (
        "warning: git clone u failed (attempt 1/3), retrying in 10s\n"
        "warning: git clone u failed (attempt 2/3), retrying in 20s\n"
    )

    fake.calls.clear()
    for attempt in retrying(RetryPolicy(attempts=5, delay=0)):
        with attempt:
            run("git", "clone", "u" if len(fake.calls) < 2 else "v")
    assert fake.calls == [["git", "clone", "u"], ["git", "clone", "u"], ["git", "clone", "v"]]

    passes.clear()
    with pytest.raises(ValueError):  # not in retry_on: no second attempt
        for attempt in retrying(RetryPolicy(delay=0)):
            with attempt:
                passes.append(1)
                raise ValueError
    assert passes == [1]


def test_die_and_defer():
    with pytest.raises(Failed, match="^boom$"):
        die("boom")
    with pytest.raises(Deferred, match="^net$"):
        defer("net")


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
    assert ensure_line("/etc/conf", "^e=", "e=5", before="^c=") is True
    assert ensure_line("/etc/conf", "^e=", "e=5", before="^c=") is False
    assert conf.read_text() == "a=1\nb=2\ne=5\nc=3\n#b=9\nd=4\n"
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


def test_network_retries_then_defers(fake, monkeypatch):
    monkeypatch.setattr(engine, "sleep", lambda seconds: None)
    engine.network("git", "clone", "x", failure="cloning x failed")
    assert fake.calls == [["git", "clone", "x"]]
    fake.answers[("git", "clone", "x")] = (128, "")
    with pytest.raises(engine.Deferred, match="^cloning x failed$"):
        engine.network("git", "clone", "x", failure="cloning x failed")
    assert len(fake.calls) == 4  # 1 + 3 attempts
