import tomllib
from pathlib import Path

import pytest

from dotfiles import engine
from dotfiles.apply import STEPS, Step, apply
from dotfiles.config import ROOT

MODULES = {
    "a": 'print("a ran")',
    "boom": 'from dotfiles.engine import die\ndie("broken")',
    "crash": "raise RuntimeError('bug')",
    "needs_boom": 'print("needs_boom ran")',
    "needs_that": 'print("needs_that ran")',
    "guarded": 'from dotfiles.engine import os_guard\nos_guard("nowhere")\nprint("guarded ran")',
    "net": 'from dotfiles.engine import defer\ndefer("cloning x failed")',
    "note": 'from dotfiles.engine import notice\nnotice("reboot")',
    "off": 'raise AssertionError("a disabled feature was imported")',
    "z": 'print("z ran")',
}


@pytest.fixture
def package(tmp_path, monkeypatch) -> str:
    """A package of fake features: each module's apply() runs its snippet."""
    pkg = tmp_path / "pkg" / "fakefeatures"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, body in MODULES.items():
        if name == "off":  # fails on import, not on apply
            (pkg / f"{name}.py").write_text(body + "\n")
            continue
        code = "\n".join("    " + line for line in body.splitlines())
        (pkg / f"{name}.py").write_text(f"def apply(cfg):\n{code}\n")
    monkeypatch.syspath_prepend(str(tmp_path / "pkg"))
    return "fakefeatures"


@pytest.fixture
def root(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "hosts").mkdir(parents=True)
    (root / "defaults.toml").write_text("[features]\non.enabled = true\noff.enabled = false\n")
    (root / "hosts/h.toml").write_text("")
    return root


def test_order_gates_failures_and_notices(root, package, capsys):
    steps = [
        Step("a", "on"),
        Step("off", "off"),
        Step("boom", None),
        Step("guarded", None),
        Step("needs_boom", None, needs=("boom",)),
        Step("needs_that", None, needs=("needs_boom",)),
        Step("net", None, needs=("off",)),  # a disabled need does not block
        Step("crash", None),
        Step("note", None),
        Step("dotfiles", None),
        Step("z", None, needs=("guarded", "net", "dotfiles")),
    ]
    assert apply("h", root, steps=steps, package=package) == 1
    out, err = capsys.readouterr()
    assert out == (
        "a ran\n"
        "z ran\n"
        "\nNotices from this apply:\n"
        "    cloning x failed (network?) — the next apply retries\n"
        "    reboot\n"
    )
    assert err == (
        "error: boom: broken\n"
        "error: needs_boom: not run, boom failed\n"
        "error: needs_that: not run, needs_boom failed\n"
        "warning: cloning x failed (network?) — the next apply retries\n"
        "error: crash: bug\n"
        "warning: reboot\n"
    )


def test_clean_run_is_silent(root, package, capsys):
    assert (
        apply("h", root, steps=[Step("guarded", "on"), Step("dotfiles", None)], package=package)
        == 0
    )
    assert capsys.readouterr() == ("", "")


def test_notices_survive_ctrl_c(root, package, capsys, monkeypatch):
    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr("dotfiles.apply._deploy", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply("h", root, steps=[Step("note", None), Step("dotfiles", None)], package=package)
    assert capsys.readouterr().out.endswith("Notices from this apply:\n    reboot\n")


def test_steps_are_consistent():
    defaults = tomllib.loads((ROOT / "defaults.toml").read_text())["features"]
    seen = set()
    for step in STEPS:
        assert step.module == "dotfiles" or (ROOT / f"dotfiles/features/{step.module}.py").exists()
        assert step.gate is None or step.gate in defaults, step
        assert set(step.needs) <= seen, f"{step.module} needs a later or unknown step"
        seen.add(step.module)
    assert len(seen) == len(STEPS)


@pytest.fixture
def arch(monkeypatch):
    monkeypatch.setattr(engine.platform, "freedesktop_os_release", lambda: {"ID": "arch"})


def test_nobeep(arch, monkeypatch, capsys):
    from dotfiles.features import nobeep

    cfg = {"features": {"nobeep": {"enabled": True}}}
    monkeypatch.setattr(engine, "DRY_RUN", True)
    nobeep.apply(cfg)
    assert capsys.readouterr().out == "-> /etc/modprobe.d/nobeep.conf (missing)\n"
    assert not engine.SYSROOT.exists()

    # Tests never become root: the install that would set root:root is only recorded.
    monkeypatch.setattr(engine, "DRY_RUN", False)
    calls = []
    monkeypatch.setattr(engine, "_run", lambda argv, **kw: calls.append(argv))
    monkeypatch.setenv("SUDO_CMD", "")
    nobeep.apply(cfg)
    dst = str(engine.SYSROOT / "etc/modprobe.d/nobeep.conf")
    assert calls[0][:8] == ["install", "-D", "-m", "644", "-o", "root", "-g", "root"]
    assert calls[0][-1] == dst
    capsys.readouterr()

    conf = Path(dst)
    conf.parent.mkdir(parents=True)
    conf.write_text("blacklist pcspkr\n")
    conf.chmod(0o644)
    monkeypatch.setattr(engine, "_owner", lambda path: "root:root")
    nobeep.apply(cfg)
    assert capsys.readouterr().out == ""


def test_nobeep_is_arch_only(monkeypatch):
    from dotfiles.features import nobeep

    monkeypatch.setattr(engine.platform, "freedesktop_os_release", lambda: {"ID": "ubuntu"})
    with pytest.raises(engine.Skip):
        nobeep.apply({})


def test_dry_run_on_a_real_host_never_calls_sudo(arch, monkeypatch, capsys):
    """hyper-lin end to end: nothing is run, nothing written, sudo untouched."""
    monkeypatch.setattr(engine, "_run", lambda argv, **kw: pytest.fail(f"ran {argv}"))
    assert apply("hyper-lin", dry_run=True) == 0
    out = capsys.readouterr().out
    assert "-> /etc/modprobe.d/nobeep.conf (missing)\n" in out
    assert "-> ~/.zshrc (missing)\n" in out
    assert not (Path.home() / ".zshrc").exists()
