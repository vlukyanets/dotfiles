"""The command line: which config each command reads."""

import sys

import pytest

from dotfiles.cli import main
from dotfiles.layout import Layout, local_config


def run(monkeypatch, capsys, *argv: str) -> tuple[int, str, str]:
    monkeypatch.setattr(sys, "argv", ["dotfiles", *argv])
    code = main()
    return code, *capsys.readouterr()


def test_init_then_every_command_reads_the_machine_config(monkeypatch, capsys):
    assert run(monkeypatch, capsys, "config") == (
        1,
        "",
        (
            "error: no ~/.config/dotfiles/config.toml — run dotfiles init <host>, "
            "or pass --source <checkout>\n"
        ),
    )
    local = local_config()
    assert run(monkeypatch, capsys, "init", "hyper") == (
        0,
        "-> ~/.config/dotfiles/config.toml (missing)\n",
        "",
    )
    assert run(monkeypatch, capsys, "init", "hyper")[1] == "nothing to change\n"
    _, repo, _ = run(monkeypatch, capsys, "config", "--host", "hyper")
    assert run(monkeypatch, capsys, "config") == (0, repo, "")
    # The machine config wins until --source or --host points at a checkout.
    local.write_text(local.read_text().replace('"Valentin Lukyanets"', '"Someone Else"'))
    _, mine, _ = run(monkeypatch, capsys, "config")
    assert 'name = "Someone Else"' in mine
    assert run(monkeypatch, capsys, "config", "--source", str(Layout.root))[1] != mine
    assert run(monkeypatch, capsys, "check")[1].split()[-2:] == ["local", "ok"]


@pytest.mark.parametrize("command", ["init", "config", "render", "deploy", "apply", "check"])
def test_source_must_be_a_checkout(monkeypatch, capsys, tmp_path, command):
    extra = ["--out", str(tmp_path / "out")] if command == "render" else []
    code, _, err = run(monkeypatch, capsys, command, "--source", str(tmp_path), *extra)
    assert code == 1
    assert f"{tmp_path}: not a dotfiles checkout (no hosts/)" in err
