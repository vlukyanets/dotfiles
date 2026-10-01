import os
import tomllib
from pathlib import Path

import pytest

from dotfiles import engine
from dotfiles.feature import classes
from dotfiles.layout import Layout
from dotfiles.platforms.arch import ArchLinuxOs
from dotfiles.platforms.arch.features.packaging import _jobs


def defaults(**features) -> dict:
    """The schema's config with FEATURES' settings changed, tables merged."""
    cfg = tomllib.loads(Layout().defaults.read_text())
    for name, settings in features.items():
        for key, value in settings.items():
            table = cfg["features"][name]
            if isinstance(value, dict):
                table[key].update(value)
            else:
                table[key] = value
    return cfg


def apply(name: str, cfg: dict | None = None) -> None:
    """Arch's feature NAME applied with CFG."""
    cfg = cfg or defaults()
    classes(ArchLinuxOs)[name](cfg["features"][name], ArchLinuxOs(engine.current())).apply()


def write(name: str, text: str):
    real = engine.current().files.path(name)
    real.parent.mkdir(parents=True, exist_ok=True)
    real.write_text(text)
    return real


def settings(name: str) -> list[str]:
    """The lines of NAME under SYSROOT that are not comments."""
    return [
        line
        for line in engine.current().files.path(name).read_text().splitlines()
        if line[:1] != "#"
    ]


PACMAN_CONF = "[options]\nParallelDownloads = 5\n\n[core]\nInclude = /etc/pacman.d/mirrorlist\n"


def test_packaging_with_nothing_set_touches_nothing(machine, capsys):
    conf = write("/etc/pacman.conf", PACMAN_CONF)
    apply("packaging")
    assert conf.read_text() == PACMAN_CONF
    assert not engine.current().files.path("/etc/pacman.conf.d").exists()
    assert not engine.current().files.path("/etc/makepkg.conf.d").exists()
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_packaging_writes_only_the_drop_ins_of_what_is_set(machine, capsys):
    conf = write("/etc/pacman.conf", PACMAN_CONF)
    apply("packaging", defaults(packaging={"pacman": {"flags": ["Color"]}}))
    assert settings("/etc/pacman.conf.d/options.conf") == ["Color"]
    # Options after the first repository section would be ignored.
    assert conf.read_text() == PACMAN_CONF.replace(
        "[core]", "Include = /etc/pacman.conf.d/options.conf\n[core]"
    )
    assert not engine.current().files.path("/etc/pacman.conf.d/multilib.conf").exists()
    assert not engine.current().files.path("/etc/makepkg.conf.d").exists()
    apply("packaging", defaults(packaging={"makepkg": {"jobs": 4}}))
    assert settings("/etc/makepkg.conf.d/dotfiles.conf") == ['MAKEFLAGS="-j4"']


def test_packaging_writes_what_is_set(machine, monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    write("/etc/pacman.conf", PACMAN_CONF)
    pacman = {"parallel_downloads": 3, "flags": ["Color", "VerbosePkgLists"]}
    makepkg = {"jobs": "50%", "packager": "A B <a@b>", "options": ["ccache", "!debug"]}
    apply("packaging", defaults(packaging={"pacman": pacman, "makepkg": makepkg}))
    assert settings("/etc/pacman.conf.d/options.conf") == [
        "ParallelDownloads = 3",
        "Color",
        "VerbosePkgLists",
    ]
    assert settings("/etc/makepkg.conf.d/dotfiles.conf") == [
        'MAKEFLAGS="-j8"',
        'PACKAGER="A B <a@b>"',
        "OPTIONS+=(ccache !debug)",
    ]


@pytest.mark.parametrize(("value", "threads"), [(4, 4), ("50%", 8), ("1%", 1)])
def test_jobs(monkeypatch, value, threads):
    monkeypatch.setattr(os, "cpu_count", lambda: 16)
    assert _jobs(value) == threads  # a percent never below one thread


def test_packaging_multilib(machine, capsys):
    conf = write("/etc/pacman.conf", PACMAN_CONF)
    cfg = defaults(packaging={"pacman": {"multilib": True}})
    apply("packaging", cfg)
    assert conf.read_text().endswith("\nInclude = /etc/pacman.conf.d/multilib.conf\n")
    assert settings("/etc/pacman.conf.d/multilib.conf") == [
        "[multilib]",
        "Include = /etc/pacman.d/mirrorlist",
    ]
    # -Syu, not -Sy: -Sy then -S is a partial upgrade.
    assert ["pacman", "-Syuw", "--noconfirm"] in machine.calls
    assert ["pacman", "-Su", "--noconfirm"] in machine.calls
    assert "-> multilib database synced (pacman -Syu)\n" in capsys.readouterr().out
    write("/var/lib/pacman/sync/multilib.db", "")
    apply("packaging", cfg)
    assert capsys.readouterr().out == ""
    apply("packaging")  # not set: left as it is
    assert capsys.readouterr().out == ""
    apply("packaging", defaults(packaging={"pacman": {"multilib": False}}))
    # Off: the repository goes, the Include stays.
    assert settings("/etc/pacman.conf.d/multilib.conf") == []
    assert conf.read_text().endswith("\nInclude = /etc/pacman.conf.d/multilib.conf\n")
    assert capsys.readouterr().out == "-> /etc/pacman.conf.d/multilib.conf (content differs)\n"


def test_packaging_multilib_of_pacman_conf_fails_before_any_change(machine):
    multilib = "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n"
    conf = write("/etc/pacman.conf", PACMAN_CONF + multilib)
    with pytest.raises(
        engine.Failed, match=r"enables \[multilib\] itself: comment that section out"
    ):
        apply("packaging", defaults(packaging={"pacman": {"multilib": True}}))
    assert conf.read_text() == PACMAN_CONF + multilib
    assert not engine.current().files.path("/etc/pacman.conf.d").exists()
    assert machine.calls == []


def test_packaging_multilib_commented_out_or_off(machine):
    write("/etc/pacman.conf", PACMAN_CONF + "\n#[multilib]\n#Include = /etc/pacman.d/mirrorlist\n")
    apply("packaging", defaults(packaging={"pacman": {"multilib": True}}))
    assert engine.current().files.path("/etc/pacman.conf.d/multilib.conf").exists()
    # Off: a [multilib] of pacman.conf is its own business.
    write("/etc/pacman.conf", PACMAN_CONF + "\n[multilib]\nInclude = /etc/pacman.d/mirrorlist\n")
    apply("packaging")


TIMER_ON = {
    ("systemctl", "is-enabled", "reflector.timer"): (0, "enabled"),
    ("systemctl", "is-active", "reflector.timer"): (0, "active"),
}
REFRESH = ["systemctl", "start", "reflector.service"]


def test_reflector_writes_its_config_and_refreshes_once(machine, capsys):
    apply("reflector", defaults(reflector={"country": ["Germany", "United States"]}))
    assert settings("/etc/xdg/reflector/reflector.conf") == [
        "--save /etc/pacman.d/mirrorlist",
        '--country "Germany,United States"',
        "--protocol https",
        "--latest 20",
        "--sort rate",
        "--age 12",
        "--completion-percent 100",
        "--download-timeout 5",
    ]
    assert settings("/etc/systemd/system/reflector.timer.d/override.conf") == [
        "[Timer]",
        "OnCalendar=",
        "OnCalendar=weekly",
        "OnBootSec=",
        "OnBootSec=15min",
    ]
    calls = [
        c for c in machine.calls if c[0] == "systemctl" and c[1] not in ("is-enabled", "is-active")
    ]
    assert calls == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "reflector.timer"],
        REFRESH,
    ]
    assert capsys.readouterr().out.endswith("-> mirrorlist refreshed\n")
    machine.answers.update(TIMER_ON)
    machine.calls.clear()
    apply("reflector", defaults(reflector={"country": ["Germany", "United States"]}))
    assert capsys.readouterr().out == ""
    assert REFRESH not in machine.calls


def test_reflector_changed_setting_refreshes_without_reload(machine):
    machine.answers.update(TIMER_ON)
    apply("reflector")
    machine.calls.clear()
    apply("reflector", defaults(reflector={"latest": 5}))
    assert "--latest 5" in settings("/etc/xdg/reflector/reflector.conf")
    assert ["systemctl", "daemon-reload"] not in machine.calls
    assert REFRESH in machine.calls
    assert "--country" not in "".join(settings("/etc/xdg/reflector/reflector.conf"))


def test_reflector_failed_refresh_is_a_notice(machine, capsys):
    machine.answers[tuple(REFRESH)] = (1, "")
    apply("reflector")
    out, err = capsys.readouterr()
    assert "mirrorlist refreshed" not in out
    assert "refreshing the mirrorlist failed (network?)" in err
    assert engine.current().report.notices


PARU_RUNS = {("paru", "--version"): (0, "paru v2.0.4 - libalpm v15.0.0")}


def test_paru_is_built_as_the_user_and_installed_as_root(machine, monkeypatch, capsys):
    monkeypatch.setenv("SUDO_CMD", "sudo")
    built = []

    def makepkg(argv, check=False, **kwargs):
        if argv == ["makepkg", "--packagelist"]:  # paru-debug listed, never built
            names = ["paru-2.0.4-1-x86_64.pkg.tar.zst", "paru-debug-2.0.4-1-x86_64.pkg.tar.zst"]
            listed = [str(kwargs["cwd"] / name) for name in names]
            Path(listed[0]).touch()
            built.append(listed[0])
            machine.answers[tuple(argv)] = (0, "\n".join(listed))
        return machine(argv, check, **kwargs)

    monkeypatch.setattr(engine.current().shell, "execute", makepkg)
    apply("paru")
    mutations = [c for c in machine.calls if c != ["paru", "--version"]]
    assert [c[:3] for c in mutations] == [
        ["git", "clone", "--quiet"],
        ["makepkg", "--noconfirm", "--cleanbuild"],  # as the user: no sudo
        ["makepkg", "--packagelist"],
        ["sudo", "pacman", "-U"],
    ]
    assert mutations[-1] == ["sudo", "pacman", "-U", "--needed", "--noconfirm", *built]
    assert capsys.readouterr().out == "-> paru built and installed\n"


def test_paru_that_runs_is_left_alone(machine, capsys):
    machine.answers.update(PARU_RUNS)
    apply("paru")
    assert capsys.readouterr().out == ""
    assert machine.calls == [["paru", "--version"]]


def test_paru_dry_run_builds_nothing(machine, capsys):
    engine.current().dry_run = True
    apply("paru")
    assert capsys.readouterr().out == "-> paru built and installed\n"
    assert machine.calls == [["paru", "--version"]]  # the check only


def test_paru_refuses_to_build_as_root(machine, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    with pytest.raises(engine.Failed, match="makepkg refuses root"):
        apply("paru")


RUSTUP_SHOW = (0, "Default host: x86_64-unknown-linux-gnu\nrustup home:  /home/u/.rustup")


def test_rustup_sets_the_toolchain_once(machine, capsys):
    machine.answers[("rustup", "show")] = RUSTUP_SHOW
    apply("rustup")
    assert machine.calls[-1] == ["rustup", "default", "stable"]
    assert capsys.readouterr().out == "-> rustup default stable (was none)\n"
    machine.answers[("rustup", "default")] = (0, "stable-x86_64-unknown-linux-gnu (default)")
    machine.calls.clear()
    apply("rustup")
    assert machine.calls == [["rustup", "default"], ["rustup", "show"]]
    assert capsys.readouterr().out == ""


def test_rustup_switches_to_another_toolchain(machine, capsys):
    machine.answers[("rustup", "show")] = RUSTUP_SHOW
    machine.answers[("rustup", "default")] = (0, "stable-x86_64-unknown-linux-gnu (default)")
    apply("rustup", defaults(rustup={"toolchain": "nightly-2026-09-01"}))
    assert machine.calls[-1] == ["rustup", "default", "nightly-2026-09-01"]
    assert capsys.readouterr().out == (
        "-> rustup default nightly-2026-09-01 (was stable-x86_64-unknown-linux-gnu)\n"
    )
    # A dated nightly is not "nightly": the host alone may follow the name.
    machine.answers[("rustup", "default")] = (0, "nightly-2026-09-01-x86_64-unknown-linux-gnu")
    machine.calls.clear()
    apply("rustup", defaults(rustup={"toolchain": "nightly"}))
    assert machine.calls[-1] == ["rustup", "default", "nightly"]
