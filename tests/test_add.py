"""Tests for dotfiles add, on a fake filesystem with fake owners."""

import base64
import io
import os
from pathlib import Path

import pytest
from pyfakefs import helpers
from test_install import FakeSudo

from dotfiles import add as add_module
from dotfiles import template
from dotfiles.add import Error, add

REPO = Path("/repo")
ROOT, ALICE = 0, 1000
NAMES = {ROOT: "root", ALICE: "alice"}


@pytest.fixture(autouse=True)
def machine(fs, monkeypatch):
    """A machine with root-owned /etc, alice's home, and alice running."""
    helpers.set_uid(ALICE)
    helpers.set_gid(ALICE)
    monkeypatch.setattr(add_module, "user_name", NAMES.__getitem__)
    monkeypatch.setattr(add_module, "group_name", NAMES.__getitem__)
    monkeypatch.setattr(add_module, "sudo", FakeSudo())
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/alice/.config")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))  # for the command, see dotfiles.init

    make("/etc", 0o755, ROOT)
    make("/home", 0o755, ROOT)
    make("/home/alice", 0o755, ALICE)
    make("/home/alice/.config", 0o755, ALICE)
    make("/etc/hosts", 0o644, ROOT, b"127.0.0.1 localhost\n")
    make("/home/alice/.config/plain", 0o644, ALICE, b"plain\n")
    make("/home/alice/.config/run", 0o755, ALICE, b"#!/bin/sh\n")
    fs.create_dir(REPO)
    # The real rules, as the command reads them from the repository.
    fs.add_real_file(Path(__file__).parents[1] / "secret_leaks.toml", target_path=REPO / "secret_leaks.toml")
    yield
    helpers.reset_ids()


def as_root(function):
    def call(*args):
        helpers.set_uid(ROOT)
        try:
            return function(*args)
        finally:
            helpers.set_uid(ALICE)
    return call


@as_root
def make(path, mode, uid, contents=None):
    """Creates a directory, or a file when contents are given."""
    if contents is None:
        os.makedirs(path, exist_ok=True)
    else:
        Path(path).write_bytes(contents)
    os.chown(path, uid, uid)
    os.chmod(path, mode)


def meta(node="hyper"):
    path = REPO / "nodes" / node / ".meta"
    return path.read_text().splitlines() if path.exists() else None


def run(*paths, **kwargs):
    add(REPO, "hyper", list(paths), **kwargs)


def test_copies_files_with_git_modes(capsys):
    run("/etc/hosts", "/home/alice/.config/plain", "/home/alice/.config/run")

    node = REPO / "nodes/hyper"
    assert (node / "etc/hosts").read_bytes() == b"127.0.0.1 localhost\n"
    assert (node / "etc/hosts").stat().st_mode & 0o777 == 0o644
    assert (node / "home/alice/.config/run").stat().st_mode & 0o777 == 0o755
    assert capsys.readouterr().out.splitlines() == [
        "added nodes/hyper/etc/hosts",
        "added nodes/hyper/home/alice/.config/plain",
        "added nodes/hyper/home/alice/.config/run",
    ]
    assert meta() is None


def test_records_files_and_directories_that_differ():
    make("/etc/sudoers.d", 0o750, ROOT)
    make("/etc/sudoers.d/alice", 0o440, ROOT, b"alice ALL=(ALL) ALL\n")
    make("/home/alice/.ssh", 0o700, ALICE)
    make("/home/alice/.ssh/config", 0o600, ALICE, b"Host *\n")
    make("/etc/owned", 0o644, ALICE, b"x\n")

    run("/home/alice/.ssh/config", "/etc/sudoers.d/alice", "/etc/owned")

    assert meta() == [
        "0644 alice:alice etc/owned",
        "0750 root:root etc/sudoers.d/",
        "0440 root:root etc/sudoers.d/alice",
        "0700 alice:alice home/alice/.ssh/",
        "0600 alice:alice home/alice/.ssh/config",
    ]


def test_home_directory_itself_belongs_to_its_user():
    make("/home/alice", 0o700, ALICE)
    run("/home/alice/.config/plain")
    assert meta() == ["0700 alice:alice home/alice/"]


def test_second_run_changes_nothing(capsys):
    make("/home/alice/.ssh", 0o700, ALICE)
    make("/home/alice/.ssh/config", 0o600, ALICE, b"Host *\n")
    run("/home/alice/.ssh/config", "/etc/hosts")
    capsys.readouterr()

    run("/home/alice/.ssh/config", "/etc/hosts")

    assert capsys.readouterr().out.splitlines() == [
        "unchanged nodes/hyper/home/alice/.ssh/config",
        "unchanged nodes/hyper/etc/hosts",
    ]


def test_updates_a_copy_whose_contents_changed(capsys):
    run("/etc/hosts")
    make("/etc/hosts", 0o644, ROOT, b"changed\n")
    capsys.readouterr()

    run("/etc/hosts")

    assert (REPO / "nodes/hyper/etc/hosts").read_bytes() == b"changed\n"
    assert capsys.readouterr().out.splitlines() == ["updated nodes/hyper/etc/hosts"]


def test_updates_a_copy_that_became_executable(capsys):
    run("/etc/hosts")
    make("/etc/hosts", 0o755, ROOT, b"127.0.0.1 localhost\n")
    capsys.readouterr()

    run("/etc/hosts")

    assert (REPO / "nodes/hyper/etc/hosts").stat().st_mode & 0o777 == 0o755
    assert capsys.readouterr().out.splitlines() == ["updated nodes/hyper/etc/hosts"]


def test_line_follows_the_mode_and_goes_with_it(capsys):
    make("/home/alice/.ssh", 0o700, ALICE)
    make("/home/alice/.ssh/config", 0o600, ALICE, b"Host *\n")
    run("/home/alice/.ssh/config")

    os.chmod("/home/alice/.ssh", 0o750)
    run("/home/alice/.ssh/config")
    assert "0750 alice:alice home/alice/.ssh/" in meta()

    os.chmod("/home/alice/.ssh", 0o755)
    os.chmod("/home/alice/.ssh/config", 0o644)
    capsys.readouterr()
    run("/home/alice/.ssh/config")

    out = capsys.readouterr().out.splitlines()
    assert "meta: removed home/alice/.ssh/" in out
    assert "meta: removed home/alice/.ssh/config" in out
    assert meta() is None


def test_dry_run_writes_nothing(capsys):
    make("/etc/key", 0o600, ROOT, b"secret\n")
    run("/etc/key", dry_run=True)

    assert not (REPO / "nodes").exists()
    assert capsys.readouterr().out.splitlines() == [
        "added nodes/hyper/etc/key",
        "meta: set 0600 root:root etc/key",
    ]


def test_reads_inside_a_closed_directory_with_one_sudo_helper():
    make("/etc/sudoers.d", 0o750, ROOT)
    make("/etc/sudoers.d/alice", 0o440, ROOT, b"alice ALL=(ALL) ALL\n")
    make("/etc/sudoers.d/bob", 0o440, ROOT, b"bob ALL=(ALL) ALL\n")
    run("/etc/sudoers.d/alice", "/etc/sudoers.d/bob")
    assert (REPO / "nodes/hyper/etc/sudoers.d/alice").read_bytes() == b"alice ALL=(ALL) ALL\n"
    assert {"stat", "read"} <= set(add_module.sudo.calls)
    assert add_module.sudo.closed


def test_a_path_missing_behind_a_closed_directory():
    make("/etc/sudoers.d", 0o750, ROOT)
    with pytest.raises(Error, match="no such file: /etc/sudoers.d/nope"):
        run("/etc/sudoers.d/nope")
    assert add_module.sudo.closed


def test_reads_a_closed_file_with_sudo_and_warns(capsys):
    make("/etc/key", 0o600, ROOT, b"secret\n")
    run("/etc/key")

    assert (REPO / "nodes/hyper/etc/key").read_bytes() == b"secret\n"
    assert "/etc/key is closed to others" in capsys.readouterr().err


def test_warns_about_a_readable_file_closed_to_others(capsys):
    make("/home/alice/.config/token", 0o600, ALICE, b"token\n")
    run("/home/alice/.config/token")
    assert "token is closed to others" in capsys.readouterr().err


def test_reads_from_another_root():
    make("/mnt/etc", 0o755, ROOT)
    make("/mnt/etc/fstab", 0o644, ROOT, b"# fstab\n")
    run("/etc/fstab", root=Path("/mnt"))
    assert (REPO / "nodes/hyper/etc/fstab").read_bytes() == b"# fstab\n"


@pytest.mark.parametrize(
    "path, message",
    [
        ("etc/hosts", "not an absolute path"),
        ("/etc", "not a regular file"),
        ("/missing", "no such file"),
        ("/etc/link", "symlinks are not supported"),
    ],
)
def test_rejects_what_is_not_an_absolute_regular_file(path, message):
    as_root(os.symlink)("hosts", "/etc/link")
    with pytest.raises(Error, match=message):
        run(path)
    assert not (REPO / "nodes").exists()


def test_rejects_a_bad_node_name():
    with pytest.raises(Error):
        add(REPO, "../x", ["/etc/hosts"])


def test_command_reports_an_error(capsys):
    from dotfiles.cli import main

    assert main(["add", "hyper", "etc/hosts"]) == 1
    assert capsys.readouterr().err == "error: not an absolute path: etc/hosts\n"


# Built from pieces, so that secret scanners do not flag this file. The
# rules themselves are tested in test_secrets.py.
GITHUB_SAMPLE = "gh" + "o_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"


def test_refuses_a_file_with_a_secret():
    make("/etc/conf", 0o644, ROOT, f"# a config\npsk={GITHUB_SAMPLE}\n".encode())
    with pytest.raises(Error, match="/etc/conf:2: github-oauth") as error:
        run("/etc/hosts", "/etc/conf")
    assert GITHUB_SAMPLE not in str(error.value)
    assert not (REPO / "nodes").exists()


def test_force_copies_a_secret_and_warns(capsys):
    make("/etc/conf", 0o644, ROOT, f"token = {GITHUB_SAMPLE}\n".encode())
    run("/etc/conf", force=True)

    assert (REPO / "nodes/hyper/etc/conf").exists()
    err = capsys.readouterr().err
    assert "/etc/conf:1: github-oauth" in err
    assert GITHUB_SAMPLE not in err


def test_refuses_a_file_kept_as_a_template():
    (REPO / "nodes/hyper/etc").mkdir(parents=True)
    (REPO / "nodes/hyper/etc/hosts.tmpl").write_text("{{ hosts }}\n")

    with pytest.raises(Error, match="kept as a template, nodes/hyper/etc/hosts.tmpl"):
        run("/etc/hosts")
    assert not (REPO / "nodes/hyper/etc/hosts").exists()


def test_refuses_a_file_named_like_a_template():
    make("/etc/x.tmpl", 0o644, ROOT, b"x\n")
    with pytest.raises(Error, match="ending in .tmpl as a template: /etc/x.tmpl"):
        run("/etc/x.tmpl")



@pytest.mark.parametrize("name", [".meta", ".hooks"])
def test_refuses_a_file_named_like_the_nodes_own(name):
    make(f"/{name}", 0o644, ROOT, b"x\n")
    with pytest.raises(Error, match=f"a node keeps its own {name} there: /{name}"):
        run(f"/{name}")

VALUES = Path("/home/alice/.config/dotfiles/hyper.toml")
CONF = f"# a config\npsk={GITHUB_SAMPLE}\n".encode()


class Terminal(io.StringIO):
    def isatty(self):
        return True


def names_given(monkeypatch, *answers):
    """Answers each name asked for in turn, noting the prompts."""
    left, prompts = list(answers), []
    monkeypatch.setattr(add_module.sys, "stdin", Terminal())

    def ask(prompt):
        prompts.append(prompt)
        return left.pop(0)
    monkeypatch.setattr("builtins.input", ask)
    return prompts


def test_template_names_each_secret(monkeypatch, capsys):
    make("/etc/conf", 0o600, ROOT, CONF)
    prompts = names_given(monkeypatch, "gh_token")

    run("/etc/conf", as_template=True)

    node = REPO / "nodes/hyper"
    assert (node / "etc/conf.tmpl").read_text() == "# a config\npsk={{ gh_token }}\n"
    assert not (node / "etc/conf").exists()
    assert template.read_values(VALUES) == {"gh_token": GITHUB_SAMPLE}
    assert prompts == ["/etc/conf:2: github-oauth, name for it: "]
    assert meta() == ["0600 root:root etc/conf.tmpl"]
    out, err = capsys.readouterr()
    assert out.splitlines()[0] == "added nodes/hyper/etc/conf.tmpl"
    assert GITHUB_SAMPLE not in out + err


def test_template_takes_the_name_a_value_already_has(monkeypatch, capsys):
    template.save_value(VALUES, "gh_token", GITHUB_SAMPLE)
    make("/etc/conf", 0o644, ROOT, CONF)
    prompts = names_given(monkeypatch)

    run("/etc/conf", as_template=True)
    capsys.readouterr()
    run("/etc/conf", as_template=True)

    assert prompts == []
    assert (REPO / "nodes/hyper/etc/conf.tmpl").read_text() == "# a config\npsk={{ gh_token }}\n"
    assert capsys.readouterr().out == "unchanged nodes/hyper/etc/conf.tmpl\n"


def test_asks_again_for_a_bad_or_taken_name(monkeypatch, capsys):
    template.save_value(VALUES, "taken", "other")
    make("/etc/conf", 0o644, ROOT, CONF)
    prompts = names_given(monkeypatch, "Bad!", "taken", "fresh")

    run("/etc/conf", as_template=True)

    assert len(prompts) == 3
    assert template.read_values(VALUES) == {"taken": "other", "fresh": GITHUB_SAMPLE}
    assert "taken is taken" in capsys.readouterr().err


def test_template_dry_run_asks_and_writes_nothing(monkeypatch, capsys):
    make("/etc/conf", 0o644, ROOT, CONF)
    prompts = names_given(monkeypatch)

    run("/etc/conf", as_template=True, dry_run=True)

    assert prompts == []
    assert capsys.readouterr().out == "added nodes/hyper/etc/conf.tmpl (1 values to name)\n"
    assert not (REPO / "nodes").exists()
    assert not VALUES.exists()


def test_template_names_are_asked_only_in_a_terminal(monkeypatch):
    make("/etc/conf", 0o644, ROOT, CONF)
    monkeypatch.setattr(add_module.sys, "stdin", io.StringIO())

    with pytest.raises(Error, match="/etc/conf:2: github-oauth: the secret's name is asked in a terminal"):
        run("/etc/conf", as_template=True)
    assert not (REPO / "nodes").exists()


def test_template_of_a_file_without_secrets_is_its_copy():
    run("/etc/hosts", as_template=True)
    assert (REPO / "nodes/hyper/etc/hosts.tmpl").read_bytes() == b"127.0.0.1 localhost\n"


def test_template_refuses_a_file_kept_as_a_plain_copy():
    run("/etc/hosts")
    with pytest.raises(Error, match="kept as a plain copy, nodes/hyper/etc/hosts; git rm it first"):
        run("/etc/hosts", as_template=True)


def test_template_refuses_a_secret_not_in_its_line_as_it_is(monkeypatch):
    encoded = base64.b64encode(f"token = {GITHUB_SAMPLE}".encode()).decode()
    make("/etc/conf", 0o644, ROOT, f"blob: {encoded}\n".encode())
    names_given(monkeypatch)

    with pytest.raises(Error, match="/etc/conf:1: .*not in the line as it is"):
        run("/etc/conf", as_template=True)
    assert not (REPO / "nodes").exists()
