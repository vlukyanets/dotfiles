"""Tests for dotfiles install, on a fake filesystem with fake owners."""

import io
import os
from datetime import datetime
from pathlib import Path

import pytest
from pyfakefs import helpers

from dotfiles import install as install_module
from dotfiles import template
from dotfiles.add import Error
from dotfiles.install import install
from dotfiles.machine import Local

REPO = Path("/repo")
NODE = REPO / "nodes/hyper"
ROOT, ALICE = 0, 1000
NAMES = {ROOT: "root", ALICE: "alice"}
STAMP = "20261011-213000"


class FakeSudo:
    """The helper, here: the same calls as root, noted."""

    def __init__(self):
        self.calls = []
        self.closed = False

    def __getattr__(self, op):
        def call(*args):
            self.calls.append(op)
            helpers.set_uid(ROOT)
            helpers.set_gid(ROOT)
            try:
                return getattr(Local(), op)(*args)
            finally:
                helpers.set_uid(ALICE)
                helpers.set_gid(ALICE)
        return call

    def close(self):
        self.closed = True


@pytest.fixture(autouse=True)
def machine(fs, monkeypatch):
    """A machine with root-owned /etc, alice's home, and alice running."""
    helpers.set_uid(ALICE)
    helpers.set_gid(ALICE)
    ids = {"root": ROOT, "alice": ALICE}

    def lookup(kind):
        def find(name):
            if name not in ids:
                raise Error(f"no such {kind}: {name}")
            return ids[name]
        return find

    monkeypatch.setattr(install_module, "uid_of", lookup("user"))
    monkeypatch.setattr(install_module, "gid_of", lookup("group"))
    monkeypatch.setattr(install_module, "user_name", NAMES.__getitem__)
    monkeypatch.setattr(install_module, "group_name", NAMES.__getitem__)
    monkeypatch.setattr(install_module, "now", lambda: datetime(2026, 10, 11, 21, 30, 0))
    monkeypatch.setattr(install_module, "sudo", FakeSudo())
    monkeypatch.setenv("XDG_CONFIG_HOME", "/home/alice/.config")
    monkeypatch.setenv("DOTFILES_REPO", str(REPO))  # for the command, see dotfiles.init

    make("/etc", 0o755, ROOT)
    make("/home", 0o755, ROOT)
    make("/home/alice", 0o755, ALICE)
    fs.create_dir(NODE)
    fs.create_file(REPO / "secret_leaks.toml")
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


def node_file(rel, contents=b"new\n", mode=0o644):
    (NODE / rel).parent.mkdir(parents=True, exist_ok=True)
    (NODE / rel).write_bytes(contents)
    (NODE / rel).chmod(mode)


def node_meta(*lines):
    (NODE / ".meta").write_text("".join(line + "\n" for line in lines))


def state(path):
    """The mode and owner of path, as (mode, uid, gid)."""
    st = os.lstat(path)
    return st.st_mode & 0o7777, st.st_uid, st.st_gid


@as_root
def read(path):
    return Path(path).read_bytes()


@as_root
def snapshot():
    """Every path on the machine with its type, owner, mode and contents."""
    found = {}
    for directory, dirs, files in os.walk("/"):
        for name in dirs + files:
            path = os.path.join(directory, name)
            st = os.lstat(path)
            data = Path(path).read_bytes() if os.path.isfile(path) else None
            found[path] = (st.st_mode, st.st_uid, st.st_gid, data)
    return found


def run(**kwargs):
    install(REPO, "hyper", **kwargs)


def test_installs_a_missing_file(capsys):
    node_file("etc/x")

    run()

    assert Path("/etc/x").read_bytes() == b"new\n"
    assert state("/etc/x") == (0o644, ROOT, ROOT)
    assert capsys.readouterr().out == "installed /etc/x\n"


def test_executable_file_gets_0755():
    node_file("etc/x", mode=0o755)

    run()

    assert state("/etc/x") == (0o755, ROOT, ROOT)


def test_meta_sets_owner_and_mode():
    node_file("etc/x")
    node_meta("0600 alice:root etc/x")

    run()

    assert state("/etc/x") == (0o600, ALICE, ROOT)


def test_replaces_a_different_file_and_keeps_a_backup(capsys):
    make("/etc/x", 0o600, ROOT, b"old\n")
    node_file("etc/x")

    run()

    backup = f"/repo/.backups/hyper/{STAMP}/etc/x"
    assert read("/etc/x") == b"new\n"
    assert state("/etc/x") == (0o644, ROOT, ROOT)
    assert sorted(os.listdir("/etc")) == ["x"]
    assert read(backup) == b"old\n"
    assert state(backup) == (0o600, ALICE, ALICE)
    assert state("/repo/.backups")[0] == 0o700
    assert Path(f"/repo/.backups/hyper/{STAMP}/.meta").read_text() == "0600 root:root etc/x\n"
    assert capsys.readouterr().out == f"updated /etc/x (backup {backup})\n"


def test_one_run_keeps_its_backups_in_one_directory():
    make("/etc/x", 0o644, ROOT, b"old\n")
    make("/home/alice/y", 0o755, ALICE, b"old\n")
    node_file("etc/x")
    node_file("home/alice/y")

    run()

    backups = REPO / ".backups/hyper"
    assert os.listdir(backups) == [STAMP]
    assert (backups / STAMP / "home/alice/y").read_bytes() == b"old\n"
    assert (backups / STAMP / ".meta").read_text() == (
        "0644 root:root etc/x\n0755 alice:alice home/alice/y\n")


def test_fixes_only_the_mode(capsys):
    make("/etc/x", 0o600, ROOT, b"new\n")
    node_file("etc/x")

    run()

    assert state("/etc/x") == (0o644, ROOT, ROOT)
    assert sorted(os.listdir("/etc")) == ["x"]
    assert capsys.readouterr().out == "mode /etc/x 0600 → 0644\n"


def test_fixes_only_the_owner(capsys):
    make("/etc/x", 0o644, ALICE, b"new\n")
    node_file("etc/x")

    run()

    assert state("/etc/x") == (0o644, ROOT, ROOT)
    assert sorted(os.listdir("/etc")) == ["x"]
    assert capsys.readouterr().out == "owner /etc/x alice:alice → root:root\n"


def test_a_chown_is_followed_by_a_chmod_to_keep_setuid(capsys):
    make("/etc/x", 0o4755, ALICE, b"new\n")
    node_file("etc/x", mode=0o755)
    node_meta("4755 root:root etc/x")

    run()

    assert state("/etc/x") == (0o4755, ROOT, ROOT)
    assert capsys.readouterr().out == (
        "owner /etc/x alice:alice → root:root\nmode /etc/x 0755 → 4755\n")


def test_a_chown_keeps_setgid_when_the_group_may_not_run_the_file(capsys):
    make("/etc/x", 0o2644, ALICE, b"new\n")
    node_file("etc/x")

    run()

    assert capsys.readouterr().out == (
        "owner /etc/x alice:alice → root:root\nmode /etc/x 2644 → 0644\n")


def test_creates_missing_directories(capsys):
    node_file("etc/a/b/x")

    run()

    assert state("/etc/a") == (0o755, ROOT, ROOT)
    assert state("/etc/a/b") == (0o755, ROOT, ROOT)
    assert capsys.readouterr().out == "created /etc/a/\ncreated /etc/a/b/\ninstalled /etc/a/b/x\n"


def test_created_directory_takes_its_meta_line():
    node_file("etc/a/b/x")
    node_meta("0775 alice:root etc/a/b/")

    run()

    assert state("/etc/a") == (0o755, ROOT, ROOT)
    assert state("/etc/a/b") == (0o775, ALICE, ROOT)


def test_fixes_an_existing_directory_with_a_meta_line(capsys):
    make("/home/alice/.ssh", 0o755, ALICE)
    node_file("home/alice/.ssh/config")
    node_meta("0700 alice:alice home/alice/.ssh/")

    run()

    assert state("/home/alice/.ssh") == (0o700, ALICE, ALICE)
    assert capsys.readouterr().out == (
        "mode /home/alice/.ssh/ 0755 → 0700\ninstalled /home/alice/.ssh/config\n"
    )


def test_leaves_an_existing_directory_without_one():
    make("/etc", 0o750, ROOT)  # closed to alice: the stats go through sudo
    node_file("etc/x")

    run()

    assert state("/etc") == (0o750, ROOT, ROOT)
    assert read("/etc/x") == b"new\n"


def test_second_run_prints_nothing(capsys):
    make("/etc/y", 0o600, ROOT, b"old\n")
    node_file("etc/a/x")
    node_file("etc/y")
    node_file("home/alice/z", mode=0o755)
    node_meta("0700 root:root etc/a/")
    run()
    capsys.readouterr()

    run()

    assert capsys.readouterr().out == ""


def test_dry_run_changes_nothing(capsys):
    make("/etc/y", 0o600, ROOT, b"old\n")
    make("/etc/z", 0o600, ROOT, b"new\n")
    node_file("etc/a/x")
    node_file("etc/y")
    node_file("etc/z")
    before = snapshot()

    run(dry_run=True)
    dry = capsys.readouterr().out
    assert snapshot() == before

    run()
    assert capsys.readouterr().out == dry
    assert dry.count("\n") == 4


def test_user_file_in_a_closed_directory_goes_through_sudo():
    node_file("etc/x")
    node_meta("0644 alice:alice etc/x")

    run()

    assert Path("/etc/x").read_bytes() == b"new\n"
    assert state("/etc/x") == (0o644, ALICE, ALICE)
    assert "write" in install_module.sudo.calls


def test_a_user_directory_needs_no_sudo():
    node_file("home/alice/x")

    run()

    assert state("/home/alice/x") == (0o644, ALICE, ALICE)
    assert install_module.sudo.calls == []


def test_installs_under_another_root(capsys):
    make("/mnt", 0o755, ALICE)
    node_file("etc/x")

    run(root=Path("/mnt"))

    assert Path("/mnt/etc/x").read_bytes() == b"new\n"
    assert not Path("/etc/x").exists()
    assert capsys.readouterr().out == "created /mnt/etc/\ninstalled /mnt/etc/x\n"


def test_closes_the_helper():
    node_file("etc/x")

    run()

    assert install_module.sudo.closed


def make_symlink(target, link):
    as_root(os.symlink)(target, link)


def a_symlink_target():
    make_symlink("hosts", "/etc/x")
    node_file("etc/x")


def a_symlink_on_the_way():
    make("/srv", 0o755, ROOT)
    make_symlink("/srv", "/etc/d")
    node_file("etc/d/x")


def a_directory_where_a_file_goes():
    make("/etc/x", 0o755, ROOT)
    node_file("etc/x")


def a_file_where_a_directory_goes():
    make("/etc/d", 0o644, ROOT, b"")
    node_file("etc/d/x")


def an_unknown_user():
    node_file("etc/x")
    node_meta("0644 bob:root etc/x")


def an_unknown_group():
    node_file("etc/x")
    node_meta("0644 root:wheel etc/x")


def an_unknown_home_user():
    node_file("home/bob/x")


def a_meta_line_for_a_missing_path():
    node_file("etc/x")
    node_meta("0600 root:root etc/nope")


def a_meta_line_for_a_missing_directory():
    node_file("etc/x")
    node_meta("0700 root:root etc/nope/")


def a_meta_line_with_an_absolute_path():
    node_file("etc/x")
    node_meta("0700 alice:alice /etc/")


def a_meta_line_with_a_dotdot_part():
    node_file("etc/x")
    node_meta("0700 alice:alice etc/../../etc/")


@pytest.mark.parametrize(
    "setup, message",
    [
        (a_symlink_target, "/etc/x"),
        (a_symlink_on_the_way, "/etc/d"),
        (a_directory_where_a_file_goes, "/etc/x"),
        (a_file_where_a_directory_goes, "/etc/d"),
        (an_unknown_user, "no such user: bob"),
        (an_unknown_group, "no such group: wheel"),
        (an_unknown_home_user, "no such user: bob"),
        (a_meta_line_for_a_missing_path, "etc/nope"),
        (a_meta_line_for_a_missing_directory, "etc/nope/"),
        (a_meta_line_with_an_absolute_path, "not a path inside the node: /etc/"),
        (a_meta_line_with_a_dotdot_part, "not a path inside the node: etc/../../etc/"),
    ],
)
def test_errors_before_anything_is_written(setup, message):
    setup()
    node_file("etc/a-first")  # sorts before the others: written first, if at all
    node_file("home/alice/a-first")
    before = snapshot()

    with pytest.raises(Error, match=message):
        run()

    assert snapshot() == before
    assert install_module.sudo.closed


def test_missing_node():
    with pytest.raises(Error, match="no such node: laptop"):
        install(REPO, "laptop")


def test_missing_root():
    node_file("etc/x")

    with pytest.raises(Error, match="no such directory: /nope"):
        run(root=Path("/nope"))


def test_a_failed_operation_is_an_error(monkeypatch):
    node_file("home/alice/y")

    def refuse(*args):
        raise OSError(30, "Read-only file system")

    monkeypatch.setattr(install_module.local, "write", refuse)

    with pytest.raises(Error, match="write /home/alice/y: Read-only file system"):
        run()


VALUES = Path("/home/alice/.config/dotfiles/hyper.toml")


class Terminal(io.StringIO):
    def isatty(self):
        return True


def test_installs_a_filled_template(capsys):
    template.save_value(VALUES, "psk", "s3cret")
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")
    node_meta("0600 root:root etc/wifi.tmpl")

    run()

    assert read("/etc/wifi") == b"psk=s3cret\n"
    assert state("/etc/wifi") == (0o600, ROOT, ROOT)
    assert capsys.readouterr().out == "installed /etc/wifi\n"

    run()

    assert capsys.readouterr().out == ""


def test_asks_for_a_missing_value_and_never_prints_it(monkeypatch, capsys):
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")
    monkeypatch.setattr(template.sys, "stdin", Terminal())
    monkeypatch.setattr(template.getpass, "getpass", lambda prompt: "s3cret")

    run()

    assert read("/etc/wifi") == b"psk=s3cret\n"
    assert template.read_values(VALUES) == {"psk": "s3cret"}
    out, err = capsys.readouterr()
    assert "s3cret" not in out + err


def test_dry_run_names_what_it_cannot_fill_and_asks_nothing(monkeypatch, capsys):
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")
    monkeypatch.setattr(template.getpass, "getpass", lambda prompt: pytest.fail("asked"))

    run(dry_run=True)

    assert capsys.readouterr().out == "unfilled /etc/wifi (psk)\n"
    assert not os.path.exists("/etc/wifi")
    assert not VALUES.exists()


def test_backs_up_a_templated_file_under_its_own_name():
    template.save_value(VALUES, "psk", "new")
    make("/etc/wifi", 0o600, ROOT, b"psk=old\n")
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")
    node_meta("0600 root:root etc/wifi.tmpl")

    run()

    run_dir = REPO / f".backups/hyper/{STAMP}"
    assert read(str(run_dir / "etc/wifi")) == b"psk=old\n"
    assert (run_dir / ".meta").read_text() == "0600 root:root etc/wifi\n"


def test_a_file_and_its_template_cannot_both_be_kept():
    node_file("etc/x")
    node_file("etc/x.tmpl")

    with pytest.raises(Error, match="both etc/x and its template etc/x.tmpl"):
        run()


@pytest.fixture
def hooks(monkeypatch):
    """The commands the hooks ran, here, instead of running them."""
    ran = []
    monkeypatch.setattr(install_module, "run_hook", ran.append)
    return ran


def node_hooks(*lines):
    (NODE / ".hooks").write_text("".join(line + "\n" for line in lines))


def test_runs_each_hook_of_a_file_written_once_after_the_writes(hooks, capsys):
    make("/etc/x", 0o644, ROOT, b"old\n")
    make("/etc/same", 0o600, ROOT, b"new\n")
    node_file("etc/x")
    node_file("etc/y")
    node_file("etc/same")
    node_file("home/alice/z.tmpl", b"{{ z }}\n")
    template.save_value(VALUES, "z", "1")
    node_hooks(
        "# one line per pattern",
        "",
        "etc/*   sudo systemctl reload x",
        "etc/same  sudo never",  # only its mode changes
        "home/alice/z  systemctl --user restart z",
        "etc/y sudo systemctl reload x",
    )

    run()

    assert hooks == ["sudo systemctl reload x", "systemctl --user restart z"]
    assert not Path("/.hooks").exists()
    assert capsys.readouterr().out.endswith(
        "ran sudo systemctl reload x\nran systemctl --user restart z\n")


def test_dry_run_runs_no_hook(hooks, capsys):
    node_file("etc/x")
    node_hooks("etc/x sudo systemctl reload x")

    run(dry_run=True)

    assert hooks == []
    assert capsys.readouterr().out == "installed /etc/x\nran sudo systemctl reload x\n"


def test_runs_no_hook_under_another_root(hooks, capsys):
    make("/srv", 0o755, ALICE)
    node_file("home/alice/x")
    node_hooks("home/alice/x systemctl --user restart x")

    run(root=Path("/srv"))

    assert hooks == []
    assert capsys.readouterr().out.endswith("skipped systemctl --user restart x (the root is /srv)\n")


def test_a_hook_line_without_a_command_is_an_error(hooks):
    node_file("etc/x")
    node_hooks("etc/x")
    with pytest.raises(Error, match=r"/repo/nodes/hyper/.hooks:1: not `<pattern> <command>`"):
        run()
    assert not Path("/etc/x").exists()


def test_a_failed_hook_is_an_error():
    install_module.run_hook("true")
    with pytest.raises(Error, match="^exit 3: exited with 3$"):
        install_module.run_hook("exit 3")


def test_installs_missing_packages_first(monkeypatch, capsys):
    from dotfiles import packages
    installs = []
    monkeypatch.setattr(packages, "installed", lambda: {"base"})
    monkeypatch.setattr(packages, "install", installs.append)
    (NODE / ".packages").write_text("base\nniri\n")
    node_file("etc/x")

    run()

    assert installs == [["niri"]]
    assert not Path("/.packages").exists()
    assert capsys.readouterr().out == "installed packages niri\ninstalled /etc/x\n"
