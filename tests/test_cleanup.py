"""Tests for dotfiles cleanup, on a fake filesystem."""

import os
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from dotfiles import cleanup as cleanup_module
from dotfiles.add import Error
from dotfiles.cleanup import cleanup

REPO = Path("/repo")
BACKUPS = REPO / ".backups"
RUNS = {
    "hyper": ["20261001-090000", "20261010-090000", "20261011-213000"],
    "laptop": ["20261004-120000"],
}


@pytest.fixture(autouse=True)
def backups(fs, monkeypatch):
    monkeypatch.setattr(cleanup_module, "now", lambda: datetime(2026, 10, 12, 9, 0, 0))
    for node, runs in RUNS.items():
        for run in runs:
            fs.create_file(BACKUPS / node / run / "etc/x", contents="old\n")


def left():
    return {node: sorted(os.listdir(BACKUPS / node)) for node in RUNS}


def removed(*runs):
    return "".join(f"removed {BACKUPS / run}\n" for run in runs)


def test_removes_every_run(capsys):
    cleanup(REPO)

    assert left() == {"hyper": [], "laptop": []}
    assert capsys.readouterr().out == removed(
        "hyper/20261001-090000", "hyper/20261010-090000", "hyper/20261011-213000",
        "laptop/20261004-120000")


def test_keeps_the_last_runs_of_each_node(capsys):
    cleanup(REPO, keep=1)

    assert left() == {"hyper": ["20261011-213000"], "laptop": ["20261004-120000"]}
    assert capsys.readouterr().out == removed("hyper/20261001-090000", "hyper/20261010-090000")


def test_keep_zero_removes_every_run():
    cleanup(REPO, keep=0)
    assert left() == {"hyper": [], "laptop": []}


def test_removes_the_runs_older_than_days(capsys):
    cleanup(REPO, older_than=7)

    assert left() == {"hyper": ["20261010-090000", "20261011-213000"], "laptop": []}
    assert capsys.readouterr().out == removed("hyper/20261001-090000", "laptop/20261004-120000")


def test_dry_run_removes_nothing(capsys):
    cleanup(REPO, dry_run=True)

    assert left() == RUNS
    assert capsys.readouterr().out.count("removed") == 4


def test_without_backups_does_nothing(capsys):
    shutil.rmtree(BACKUPS)

    cleanup(REPO)

    assert capsys.readouterr().out == ""


def test_refuses_what_is_not_a_run():
    os.mkdir(BACKUPS / "hyper/notes")

    with pytest.raises(Error, match="not a backup: /repo/.backups/hyper/notes"):
        cleanup(REPO)
    assert left() == {**RUNS, "hyper": RUNS["hyper"] + ["notes"]}


def test_refuses_a_negative_number():
    with pytest.raises(Error, match="must not be negative"):
        cleanup(REPO, keep=-1)
