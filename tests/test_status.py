"""Tests for dotfiles status, on the fake machine of test_install."""

import os
from pathlib import Path

import pytest

from dotfiles import install as install_module
from dotfiles import template
from dotfiles.add import Error
from dotfiles.status import status
from test_install import REPO, VALUES, as_root, machine, make, node_file, node_meta, snapshot  # noqa: F401


def run(**kwargs):
    status(REPO, "hyper", **kwargs)


def test_a_machine_like_its_node(capsys):
    make("/etc/x", 0o644, 0, b"new\n")
    node_file("etc/x")

    run()

    assert capsys.readouterr().out == "Node hyper, root /\nNothing differs from the node.\n"


def test_lists_what_changed_on_the_machine(capsys):
    make("/etc/a", 0o644, 0, b"changed\n")
    make("/etc/b", 0o600, 0, b"new\n")
    make("/etc/c", 0o644, 1000, b"new\n")
    make("/home/alice/.ssh", 0o755, 1000)
    for rel in ("etc/a", "etc/b", "etc/c", "etc/d", "home/alice/.ssh/config"):
        node_file(rel)
    node_meta("0700 alice:alice home/alice/.ssh/")

    run()

    assert capsys.readouterr().out == (
        "Node hyper, root /\n"
        "\n"
        "Changes on the machine:\n"
        "  (dotfiles add hyper <path> keeps them; dotfiles install hyper undoes them)\n"
        "        mode:      /home/alice/.ssh/  0700 → 0755\n"
        "        modified:  /etc/a\n"
        "        mode:      /etc/b  0644 → 0600\n"
        "        owner:     /etc/c  root:root → alice:alice\n"
        "        missing:   /etc/d\n"
        "        missing:   /home/alice/.ssh/config\n"
    )


def test_a_missing_directory_shows_as_its_files(capsys):
    node_file("etc/a/b/x")

    run()

    assert "/etc/a/" not in capsys.readouterr().out.replace("/etc/a/b/x", "")


def test_lists_directories_off_their_defaults_without_a_meta_line(capsys):
    make("/etc/d", 0o750, 0)
    make("/etc/d/x", 0o644, 0, b"new\n")
    node_file("etc/d/x")

    run()

    assert capsys.readouterr().out == (
        "Node hyper, root /\n"
        "\n"
        "Directories off their defaults, with no .meta line:\n"
        "  (dotfiles add records them with the next file added under them)\n"
        "        mode:      /etc/d/  0755 → 0750\n"
    )


def test_shows_the_real_mode_of_a_setuid_file(capsys):
    make("/etc/x", 0o4755, 1000, b"new\n")
    node_file("etc/x", mode=0o755)
    node_meta("4755 root:root etc/x")

    run()

    out = capsys.readouterr().out
    assert "owner:     /etc/x  root:root → alice:alice\n" in out
    assert "mode:" not in out


def test_verbose_shows_a_diff(capsys):
    make("/etc/x", 0o644, 0, b"one\nthree")
    make("/etc/bin", 0o644, 0, b"\0\1")
    node_file("etc/x", b"one\ntwo\n")
    node_file("etc/bin", b"\0\2")

    run(verbose=True)

    out = capsys.readouterr().out
    assert out.endswith(
        "\nBinary files nodes/hyper/etc/bin and /etc/bin differ\n"
        "\n"
        "--- nodes/hyper/etc/x\n"
        "+++ /etc/x\n"
        "@@ -1,2 +1,2 @@\n"
        " one\n"
        "-two\n"
        "+three\n"
        "\\ No newline at end of file\n"
    )


def test_reads_a_closed_file_with_sudo_and_writes_nothing(capsys):
    make("/etc/key", 0o600, 0, b"old\n")
    node_file("etc/key")
    node_meta("0600 root:root etc/key")
    before = snapshot()

    run()

    assert "modified:  /etc/key" in capsys.readouterr().out
    assert "read" in install_module.sudo.calls
    assert install_module.sudo.closed
    assert snapshot() == before


def test_compares_another_root(capsys):
    make("/mnt/etc", 0o755, 0)
    node_file("etc/x")

    run(root=Path("/mnt"))

    assert "missing:   /mnt/etc/x" in capsys.readouterr().out


def test_stops_on_what_install_stops_on():
    as_root(os.symlink)("hosts", "/etc/x")
    node_file("etc/x")

    with pytest.raises(Error, match="symlinks are not supported: /etc/x"):
        run()


def test_command_runs_status(capsys):
    from dotfiles.cli import main

    assert main(["status", "nope"]) == 1
    assert "no such node: nope" in capsys.readouterr().err


def test_compares_a_template_filled_in(capsys):
    template.save_value(VALUES, "psk", "s3cret")
    make("/etc/wifi", 0o644, 0, b"psk=s3cret\n")
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")

    run()

    assert capsys.readouterr().out == "Node hyper, root /\nNothing differs from the node.\n"


def test_a_template_without_its_values(capsys):
    make("/etc/wifi", 0o600, 0, b"psk=s3cret\n")
    node_file("etc/wifi.tmpl", b"psk={{ psk }} {{ id }}\n")

    run()

    out = capsys.readouterr().out
    assert "        unfilled:  /etc/wifi  (psk, id)\n" in out
    assert "        mode:      /etc/wifi  0644 → 0600\n" in out


def test_verbose_shows_no_diff_of_a_template(capsys):
    template.save_value(VALUES, "psk", "s3cret")
    make("/etc/wifi", 0o644, 0, b"psk=other\n")
    node_file("etc/wifi.tmpl", b"psk={{ psk }}\n")

    run(verbose=True)

    out = capsys.readouterr().out
    assert "        modified:  /etc/wifi\n" in out
    assert out.endswith("\nTemplate nodes/hyper/etc/wifi.tmpl and /etc/wifi differ;"
                        " the diff would show its values\n")
    assert "s3cret" not in out and "other" not in out
