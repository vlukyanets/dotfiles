"""Tests for dotfiles status, on the fake machine of test_install."""

import os
from pathlib import Path

import pytest
from test_install import (  # noqa: F401
    REPO,
    VALUES,
    as_root,
    host_file,
    host_link,
    host_meta,
    machine,
    make,
    own_link,
    snapshot,
)

from dotfiles import install as install_module
from dotfiles import template
from dotfiles.add import Error
from dotfiles.status import status


def run(**kwargs):
    status(REPO, "hyper", **kwargs)


def test_a_machine_like_its_host(capsys):
    make("/etc/x", 0o644, 0, b"new\n")
    host_file("etc/x")

    run()

    assert capsys.readouterr().out == "Host hyper, root /\nNothing differs from the host.\n"


def test_lists_what_changed_on_the_machine(capsys):
    make("/etc/a", 0o644, 0, b"changed\n")
    make("/etc/b", 0o600, 0, b"new\n")
    make("/etc/c", 0o644, 1000, b"new\n")
    make("/home/alice/.ssh", 0o755, 1000)
    for rel in ("etc/a", "etc/b", "etc/c", "etc/d", "home/alice/.ssh/config"):
        host_file(rel)
    host_meta("0700 alice:alice home/alice/.ssh/")

    run()

    assert capsys.readouterr().out == (
        "Host hyper, root /\n"
        "\n"
        "Changes on the machine:\n"
        "  (dotfiles add --host hyper <path> keeps them; dotfiles install --host hyper undoes them)\n"
        "        mode:      /home/alice/.ssh/  0700 → 0755\n"
        "        modified:  /etc/a\n"
        "        mode:      /etc/b  0644 → 0600\n"
        "        owner:     /etc/c  root:root → alice:alice\n"
        "        missing:   /etc/d\n"
        "        missing:   /home/alice/.ssh/config\n"
    )


def test_a_missing_directory_shows_as_its_files(capsys):
    host_file("etc/a/b/x")

    run()

    assert "/etc/a/" not in capsys.readouterr().out.replace("/etc/a/b/x", "")


def test_lists_directories_off_their_defaults_without_a_meta_line(capsys):
    make("/etc/d", 0o750, 0)
    make("/etc/d/x", 0o644, 0, b"new\n")
    host_file("etc/d/x")

    run()

    assert capsys.readouterr().out == (
        "Host hyper, root /\n"
        "\n"
        "Directories off their defaults, with no .meta line:\n"
        "  (dotfiles add records them with the next file added under them)\n"
        "        mode:      /etc/d/  0755 → 0750\n"
    )


def test_shows_the_real_mode_of_a_setuid_file(capsys):
    make("/etc/x", 0o4755, 1000, b"new\n")
    host_file("etc/x", mode=0o755)
    host_meta("4755 root:root etc/x")

    run()

    out = capsys.readouterr().out
    assert "owner:     /etc/x  root:root → alice:alice\n" in out
    assert "mode:" not in out


def test_verbose_shows_a_diff(capsys):
    make("/etc/x", 0o644, 0, b"one\nthree")
    make("/etc/bin", 0o644, 0, b"\0\1")
    host_file("etc/x", b"one\ntwo\n")
    host_file("etc/bin", b"\0\2")

    run(verbose=True)

    out = capsys.readouterr().out
    assert out.endswith(
        "\nBinary files hosts/hyper/etc/bin and /etc/bin differ\n"
        "\n"
        "--- hosts/hyper/etc/x\n"
        "+++ /etc/x\n"
        "@@ -1,2 +1,2 @@\n"
        " one\n"
        "-two\n"
        "+three\n"
        "\\ No newline at end of file\n"
    )


def test_reads_a_closed_file_with_sudo_and_writes_nothing(capsys):
    make("/etc/key", 0o600, 0, b"old\n")
    host_file("etc/key")
    host_meta("0600 root:root etc/key")
    before = snapshot()

    run()

    assert "modified:  /etc/key" in capsys.readouterr().out
    assert "read" in install_module.sudo.calls
    assert install_module.sudo.closed
    assert snapshot() == before


def test_compares_another_root(capsys):
    make("/mnt/etc", 0o755, 0)
    host_file("etc/x")

    run(root=Path("/mnt"))

    assert "missing:   /mnt/etc/x" in capsys.readouterr().out


def test_stops_on_what_install_stops_on():
    make("/srv", 0o755, 0)
    as_root(os.symlink)("/srv", "/etc/d")
    host_file("etc/d/x")

    with pytest.raises(Error, match="a symlink, not a directory: /etc/d"):
        run()


def test_shows_where_a_symlink_points(capsys):
    as_root(os.symlink)("/y", "/etc/a")
    host_link("etc/a", "/x")
    make("/etc/b", 0o644, 0, b"new\n")
    host_link("etc/b", "/x")
    make("/etc/secret", 0o600, 0, b"secret\n")
    as_root(os.symlink)("/etc/secret", "/etc/c")
    host_file("etc/c")
    host_link("etc/d", "/x")
    as_root(os.symlink)("/dangling", "/etc/e")
    own_link("/etc/e", 1000)
    host_link("etc/e", "/dangling")

    run()

    assert capsys.readouterr().out.endswith(
        "        target:    /etc/a  /x → /y\n"
        "        target:    /etc/b  /x → (a file)\n"
        "        target:    /etc/c  (a file) → /etc/secret\n"
        "        missing:   /etc/d\n"
    )
    assert "read" not in install_module.sudo.calls


def test_command_runs_status(capsys):
    from dotfiles.cli import main

    assert main(["status", "--host", "nope"]) == 1
    assert "no such host: nope" in capsys.readouterr().err


def test_compares_a_template_filled_in(capsys):
    template.save_value(VALUES, "psk", "s3cret")
    make("/etc/wifi", 0o644, 0, b"psk=s3cret\n")
    host_file("etc/wifi.tmpl", b"psk={{ psk }}\n")

    run()

    assert capsys.readouterr().out == "Host hyper, root /\nNothing differs from the host.\n"


def test_a_template_without_its_values(capsys):
    make("/etc/wifi", 0o600, 0, b"psk=s3cret\n")
    host_file("etc/wifi.tmpl", b"psk={{ psk }} {{ id }}\n")

    run()

    out = capsys.readouterr().out
    assert "        unfilled:  /etc/wifi  (psk, id)\n" in out
    assert "        mode:      /etc/wifi  0644 → 0600\n" in out


def test_verbose_shows_a_template_diff_with_its_values_hidden(capsys):
    template.save_value(VALUES, "psk", "s3cret")
    template.save_value(VALUES, "psk_long", "s3cret-and-more")
    make("/etc/wifi", 0o644, 0, b"psk=s3cret\nlong=s3cret-and-more\nmode=b\n")
    host_file("etc/wifi.tmpl", b"psk={{ psk }}\nlong={{ psk_long }}\nmode=a\n")

    run(verbose=True)

    out = capsys.readouterr().out
    assert "s3cret" not in out
    assert out.endswith(
        "\n--- hosts/hyper/etc/wifi.tmpl\n"
        "+++ /etc/wifi (values hidden)\n"
        "@@ -1,3 +1,3 @@\n"
        " psk={{ psk }}\n"
        " long={{ psk_long }}\n"
        "-mode=a\n"
        "+mode=b\n"
    )


def test_lists_the_packages_the_machine_lacks(monkeypatch, capsys):
    from dotfiles import packages
    monkeypatch.setattr(packages, "installed", lambda: {"base"})
    monkeypatch.setattr(packages, "explicit", lambda: {"base"})
    (REPO / "hosts/hyper/.packages").write_text("base\nniri\n")

    run()

    assert capsys.readouterr().out == (
        "Host hyper, root /\n"
        "\nPackages the machine lacks:\n"
        "  (dotfiles install --host hyper installs them; dotfiles forget --host hyper --package <name> drops them)\n"
        "        package:   niri\n")


def test_lists_the_packages_not_in_the_host(monkeypatch, capsys):
    from dotfiles import packages
    monkeypatch.setattr(packages, "installed", lambda: {"base", "git", "niri", "vim"})
    monkeypatch.setattr(packages, "explicit", lambda: {"base", "vim", "git"})
    (REPO / "hosts/hyper/.packages").write_text("base\nniri\n")

    run()

    assert capsys.readouterr().out == (
        "Host hyper, root /\n"
        "\nPackages not in the host:\n"
        "  (dotfiles add --host hyper --package <name> keeps them; removing them is yours)\n"
        "        package:   git\n"
        "        package:   vim\n")


def test_another_root_has_no_packages_to_lack(monkeypatch, capsys):
    from dotfiles import packages
    monkeypatch.setattr(packages, "installed", lambda: {"vim"})
    monkeypatch.setattr(packages, "explicit", lambda: {"vim"})
    (REPO / "hosts/hyper/.packages").write_text("niri\n")
    make("/srv", 0o755, 0)

    run(root=Path("/srv"))

    assert capsys.readouterr().out.endswith("Nothing differs from the host.\n")
