import subprocess

import pytest

from dotfiles import engine, retry
from dotfiles.engine import Deferred, Failed, defer, die
from dotfiles.retry import RetryPolicy, retrying


def shell() -> engine.Shell:
    return engine.current().shell


def files() -> engine.Files:
    return engine.current().files


def report() -> engine.Report:
    return engine.current().report


def test_as_root_prefix(fake, monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "sudo -n")
    shell().run("true")
    with shell().as_root():
        shell().run("true")
        with shell().as_root():
            shell().run("true")
        shell().run("true", cwd="/")
        shell().output("check")  # checks never get root
    shell().run("true")
    monkeypatch.setenv("SUDO_CMD", "")
    with shell().as_root():
        shell().run("true")
    monkeypatch.setattr(engine.os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_CMD", "sudo")
    with shell().as_root():
        shell().run("true")
    assert fake.calls == [
        ["true"],
        ["sudo", "-n", "true"],
        ["sudo", "-n", "true"],
        ["sudo", "-n", "true"],
        ["check"],
        ["true"],
        ["true"],
        ["true"],
    ]


def test_sudo_from_conftest_fails():
    with pytest.raises(subprocess.CalledProcessError), shell().as_root():
        shell().run("true")


def test_root_commands_share_one_process(monkeypatch):
    monkeypatch.setenv("SUDO_CMD", "env")  # the real path, without root
    parent = ["python3", "-c", "import os; print(os.getppid())"]
    with shell().as_root():
        first = shell().run(*parent, capture_output=True).stdout
        assert shell().run(*parent, capture_output=True).stdout == first
        with pytest.raises(subprocess.CalledProcessError):
            shell().run("false")
        with pytest.raises(FileNotFoundError):
            shell().run("no-such-program")
    assert first.strip() != str(engine.os.getpid())


def test_mutations_must_succeed(fake):
    fake.answers[("false",)] = (1, "")
    with pytest.raises(subprocess.CalledProcessError):
        shell().run("false")


def test_dry_run_runs_nothing(fake, monkeypatch):
    engine.current().dry_run = True
    with shell().as_root():
        shell().run("rm", "-rf", "/")
    shell().run("touch", "x")
    assert fake.calls == []


def test_output():
    assert shell().output("printf", "a\\nb\\n") == "a\nb"
    assert shell().output("sh", "-c", "echo disabled; exit 1") == "disabled"
    assert shell().output("no-such-command-here") is None


def test_retry_policy_waits():
    assert [RetryPolicy().wait(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 60]
    assert RetryPolicy(delay=1, backoff=3, max_delay=5).wait(3) == 5


def test_retrying_repeats_the_whole_block(fake, monkeypatch, capsys):
    slept = []
    monkeypatch.setattr(retry, "sleep", slept.append)
    fake.answers[("git", "clone", "u")] = (1, "")
    passes = []
    with pytest.raises(subprocess.CalledProcessError):
        for attempt in retrying(report()):
            with attempt:
                passes.append("mktemp")
                shell().run("git", "clone", "u")
    assert passes == ["mktemp"] * 3 and slept == [10, 20]
    assert capsys.readouterr().err == (
        "warning: git clone u failed (attempt 1/3), retrying in 10s\n"
        "warning: git clone u failed (attempt 2/3), retrying in 20s\n"
    )

    fake.calls.clear()
    for attempt in retrying(report(), RetryPolicy(attempts=5, delay=0)):
        with attempt:
            shell().run("git", "clone", "u" if len(fake.calls) < 2 else "v")
    assert fake.calls == [["git", "clone", "u"], ["git", "clone", "u"], ["git", "clone", "v"]]

    passes.clear()
    with pytest.raises(ValueError):  # not in retry_on: no second attempt
        for attempt in retrying(report(), RetryPolicy(delay=0)):
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
    report().notice("log out and back in")
    assert capsys.readouterr().err == "warning: log out and back in\n"
    report().flush()
    assert capsys.readouterr().out == "\nNotices from this apply:\n    log out and back in\n"
    report().flush()
    assert capsys.readouterr().out == ""


def me() -> str:
    return engine._owner(files().path("/").parent)


def test_ensure_file_changes_once(capsys):
    real = files().path("/") / "etc/deep/er/f.conf"
    assert files().ensure("/etc/deep/er/f.conf", "a\n", 0o600, owner=me()) is True
    assert files().ensure("/etc/deep/er/f.conf", b"a\n", 0o600, owner=me()) is False
    assert real.read_text() == "a\n" and oct(real.stat().st_mode & 0o777) == "0o600"
    real.write_text("b\n")
    assert files().ensure("/etc/deep/er/f.conf", "a\n", 0o600) is True
    real.chmod(0o644)
    assert files().ensure("/etc/deep/er/f.conf", "a\n", 0o600) is True
    assert files().ensure("/etc/deep/er/f.conf", "a\n", 0o600) is False
    assert capsys.readouterr().out == (
        "-> /etc/deep/er/f.conf (missing)\n"
        "-> /etc/deep/er/f.conf (content differs)\n"
        "-> /etc/deep/er/f.conf (mode 644)\n"
    )


def test_ensure_file_goes_to_root_only_when_needed():
    locked = files().path("/") / "etc"
    locked.mkdir(parents=True)
    locked.chmod(0o555)
    try:
        with pytest.raises(subprocess.CalledProcessError) as e:  # SUDO_CMD=false
            files().ensure("/etc/f", "x\n")
        assert e.value.cmd[0] == "false"  # the root process never started
        with pytest.raises(subprocess.CalledProcessError):
            files().ensure("/tmp-owned-by-root", "x\n", owner="root:root")
    finally:
        locked.chmod(0o755)


def test_dry_run_reports_and_writes_nothing(monkeypatch, capsys):
    engine.current().dry_run = True
    assert files().ensure("/etc/f", "x\n", owner="root:root") is True
    assert files().line("/etc/g", "^x=", "x=1") is True
    assert files().symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is True
    assert not files().path("/").exists()
    assert capsys.readouterr().out == (
        "-> /etc/f (missing)\n-> /etc/g (missing)\n-> /etc/localtime -> /usr/share/zoneinfo/UTC\n"
    )


def test_ensure_line():
    conf = files().path("/") / "etc/conf"
    conf.parent.mkdir(parents=True)
    conf.write_text("a=1\n#b=2\nc=3\n#b=9\n")
    conf.chmod(0o600)
    assert files().line("/etc/conf", "^#?b=", "b=2") is True
    assert files().line("/etc/conf", "^#?b=", "b=2") is False
    assert conf.read_text() == "a=1\nb=2\nc=3\n#b=9\n"
    assert files().line("/etc/conf", "^d=", "d=4") is True
    assert files().line("/etc/conf", "^d=", "d=4") is False
    assert conf.read_text().endswith("#b=9\nd=4\n")
    assert files().line("/etc/conf", "^e=", "e=5", before="^c=") is True
    assert files().line("/etc/conf", "^e=", "e=5", before="^c=") is False
    assert conf.read_text() == "a=1\nb=2\ne=5\nc=3\n#b=9\nd=4\n"
    assert oct(conf.stat().st_mode & 0o777) == "0o600"
    assert files().line("/etc/new", "^x=", "x=1") is True
    assert files().line("/etc/new", "^x=", "x=1") is False
    assert (files().path("/") / "etc/new").read_text() == "x=1\n"


def test_ensure_symlink():
    (files().path("/") / "etc").mkdir(parents=True)
    assert files().symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is True
    assert files().symlink("/usr/share/zoneinfo/UTC", "/etc/localtime") is False
    assert files().symlink("/usr/share/zoneinfo/Europe/Berlin", "/etc/localtime") is True
    assert (files().path("/") / "etc/localtime").readlink().as_posix() == (
        "/usr/share/zoneinfo/Europe/Berlin"
    )


def test_ensure_line_of_a_file_only_root_reads():
    conf = files().path("/") / "etc/secret"
    conf.parent.mkdir(parents=True)
    conf.write_text("x=1\n")
    conf.chmod(0o000)
    try:
        with pytest.raises(Failed, match="^/etc/secret: not readable without root"):
            files().line("/etc/secret", "^x=", "x=2")
    finally:
        conf.chmod(0o600)


def test_a_missing_program_is_not_retried(monkeypatch):
    monkeypatch.setattr(retry, "sleep", lambda seconds: pytest.fail("retried"))
    with pytest.raises(FileNotFoundError):
        for attempt in retrying(report()):
            with attempt:
                shell().run("no-such-program-here")
