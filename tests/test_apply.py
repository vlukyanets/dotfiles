import sys
import tomllib
from pathlib import Path

import pytest

from dotfiles import engine
from dotfiles.apply import DEPLOY, apply, steps
from dotfiles.config import ROOT, ConfigError

# name -> (declarations, body of apply)
MODULES = {
    "a": ('GATE = "on"', 'print("a ran")'),
    "off": (
        'GATE = "off"\nPROVIDES = ("offcap",)',
        'raise AssertionError("a disabled feature ran")',
    ),
    "boom": (
        'GATE = None\nPROVIDES = ("boomcap",)',
        'from dotfiles.engine import die\ndie("broken")',
    ),
    "crash": ("GATE = None", "raise RuntimeError('bug')"),
    "guarded": (
        'GATE = None\nPROVIDES = ("g",)',
        'from dotfiles.engine import os_guard\nos_guard("nowhere")\nprint("guarded ran")',
    ),
    "needs_boom": (
        'GATE = None\nPROVIDES = ("nb",)\nREQUIRES = ("boomcap",)',
        'print("needs_boom ran")',
    ),
    "needs_that": ('GATE = None\nREQUIRES = ("nb",)', 'print("needs_that ran")'),
    # a disabled provider does not block
    "net": (
        'GATE = None\nPROVIDES = ("netcap",)\nREQUIRES = ("offcap",)',
        'from dotfiles.engine import defer\ndefer("cloning x failed")',
    ),
    "note": ("GATE = None", 'from dotfiles.engine import notice\nnotice("reboot")'),
    "z": ('GATE = None\nREQUIRES = ("g", "netcap", "dotfiles")', 'print("z ran")'),
}


def make_package(tmp_path, monkeypatch, modules: dict[str, tuple[str, str]]) -> str:
    """A package of fake features: each module's apply() runs its snippet."""
    pkg = tmp_path / "pkg" / "fakefeatures"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, (head, body) in modules.items():
        code = "\n".join("    " + line for line in body.splitlines())
        (pkg / f"{name}.py").write_text(f"{head}\n\n\ndef apply(cfg):\n{code}\n")
    monkeypatch.syspath_prepend(str(tmp_path / "pkg"))
    for name in [m for m in sys.modules if m.split(".")[0] == "fakefeatures"]:
        monkeypatch.delitem(sys.modules, name)  # each test imports its own package
    return "fakefeatures"


@pytest.fixture
def package(tmp_path, monkeypatch) -> str:
    return make_package(tmp_path, monkeypatch, MODULES)


@pytest.fixture
def root(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "hosts").mkdir(parents=True)
    (root / "defaults.toml").write_text("[features]\non.enabled = true\noff.enabled = false\n")
    (root / "hosts/h.toml").write_text("")
    return root


def test_steps_run_after_their_providers_then_by_name(package):
    got = steps(package)
    assert [s.name for s in got] == [
        "a",
        "boom",
        "crash",
        "dotfiles",
        "guarded",
        "note",
        "off",
        "needs_boom",
        "net",
        "needs_that",
        "z",
    ]
    step = {s.name: s for s in got}
    assert step["z"].after == ("dotfiles", "guarded", "net")
    gates = (step["a"].gate, step["off"].gate, step["boom"].gate, step[DEPLOY].gate)
    assert gates == ("on", "off", None, None)


def test_every_provider_of_a_capability_runs_first(root, tmp_path, monkeypatch, capsys):
    """One capability, one provider per system: the one that does not apply
    here skips, the other provides it."""
    package = make_package(
        tmp_path,
        monkeypatch,
        {
            "on_other_os": (
                'GATE = None\nPROVIDES = ("installer",)',
                'from dotfiles.engine import os_guard\nos_guard("nowhere")',
            ),
            "on_this_os": ('GATE = None\nPROVIDES = ("installer",)', 'print("installer ready")'),
            "app": ('GATE = None\nREQUIRES = ("installer",)', 'print("app ran")'),
        },
    )
    assert [s.name for s in steps(package)] == ["dotfiles", "on_other_os", "on_this_os", "app"]
    assert apply("h", root, package=package) == 0
    assert capsys.readouterr().out == "installer ready\napp ran\n"


def test_order_gates_failures_and_notices(root, package, capsys):
    assert apply("h", root, package=package) == 1
    out, err = capsys.readouterr()
    assert out == (
        "a ran\n"
        "z ran\n"
        "\nNotices from this apply:\n"
        "    reboot\n"
        "    cloning x failed (network?) — the next apply retries\n"
    )
    assert err == (
        "error: boom: broken\n"
        "error: crash: bug\n"
        "warning: reboot\n"
        "error: needs_boom: not run, boom failed\n"
        "warning: cloning x failed (network?) — the next apply retries\n"
        "error: needs_that: not run, needs_boom failed\n"
    )


@pytest.mark.parametrize(
    ("modules", "error"),
    [
        (
            {"x": ('REQUIRES = ("nope",)', "pass")},
            "fakefeatures.x: REQUIRES: nothing provides 'nope'",
        ),
        (
            {
                "x": ('PROVIDES = ("cx",)\nREQUIRES = ("cy",)', "pass"),
                "y": ('PROVIDES = ("cy",)\nREQUIRES = ("cx",)', "pass"),
            },
            "fakefeatures: REQUIRES: a cycle: ",
        ),
    ],
)
def test_bad_requires(tmp_path, monkeypatch, modules, error):
    with pytest.raises(ConfigError, match="^" + error):
        steps(make_package(tmp_path, monkeypatch, modules))


def test_clean_run_is_silent(root, tmp_path, monkeypatch, capsys):
    package = make_package(tmp_path, monkeypatch, {"guarded": MODULES["guarded"]})
    assert apply("h", root, package=package) == 0
    assert capsys.readouterr() == ("", "")


def test_notices_survive_ctrl_c(root, tmp_path, monkeypatch, capsys):
    def interrupt(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr("dotfiles.apply._deploy", interrupt)
    package = make_package(tmp_path, monkeypatch, {"alert": MODULES["note"]})  # before "dotfiles"
    with pytest.raises(KeyboardInterrupt):
        apply("h", root, package=package)
    assert capsys.readouterr().out.endswith("Notices from this apply:\n    reboot\n")


def test_real_features_are_consistent():
    defaults = tomllib.loads((ROOT / "defaults.toml").read_text())["features"]
    for step in steps():
        assert step.gate is None or step.gate in defaults, step
        assert step.module is None or callable(step.module.apply), step


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
