import os
import pwd
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from dotfiles import engine
from dotfiles.feature import classes
from dotfiles.layout import Layout
from dotfiles.platforms.arch import ArchLinuxOs
from dotfiles.platforms.arch._pacman import Pacman
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


def test_packaging_installs_pacman_contrib_only_when_asked():
    def packages(cfg):
        cls = classes(ArchLinuxOs)["packaging"]
        return cls(cfg["features"]["packaging"], ArchLinuxOs(engine.current())).packages()

    assert packages(defaults()) == []
    assert packages(defaults(packaging={"pacman": {"contrib": True}})) == ["pacman-contrib"]


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


def test_paru_is_built_from_the_aur_while_it_does_not_run(machine, monkeypatch):
    built = []
    monkeypatch.setattr(Pacman, "build", lambda self, names: built.append(names))
    apply("paru")
    assert built == [["paru"]]  # installed but not running (a libalpm bump) counts too
    machine.answers.update(PARU_RUNS)
    apply("paru")
    assert built == [["paru"]]
    assert machine.calls == [["paru", "--version"]] * 2


def test_paru_dry_run_builds_nothing(machine, capsys):
    engine.current().dry_run = True
    apply("paru")
    assert capsys.readouterr().out == "-> paru built from the AUR\n"
    assert machine.calls == [["paru", "--version"]]  # the check only


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


UNLOAD = ["modprobe", "-r", "pcspkr"]


def test_no_beep_blacklists_and_unloads_once(machine, capsys):
    engine.current().files.path("/sys/module/pcspkr").mkdir(parents=True)
    apply("no_beep")
    assert settings("/etc/modprobe.d/nobeep.conf") == ["blacklist pcspkr", "blacklist snd_pcsp"]
    assert machine.calls[-1] == UNLOAD
    assert capsys.readouterr().out.endswith("-> pcspkr unloaded\n")
    engine.current().files.path("/sys/module/pcspkr").rmdir()
    machine.calls.clear()
    apply("no_beep")
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_no_beep_driver_in_use_is_a_notice(machine, capsys):
    for module in ("pcspkr", "snd_pcsp"):
        engine.current().files.path(f"/sys/module/{module}").mkdir(parents=True)
    machine.answers[("modprobe", "-r", "pcspkr", "snd_pcsp")] = (1, "")
    apply("no_beep")
    out, err = capsys.readouterr()
    assert "unloaded" not in out
    assert "pcspkr snd_pcsp in use: the PC speaker is silent after a reboot" in err


def login_shell(monkeypatch, shell: str) -> None:
    me = SimpleNamespace(pw_name="u", pw_shell=shell)
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: me)


def home(name: str) -> Path:
    return engine.current().files.path(Path.home() / name)


CLONE = ["git", "clone", "--quiet", "--depth", "1"]


def test_zsh_clones_writes_sources_and_switches_once(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/bin/bash")
    zshrc = home(".zshrc")
    zshrc.parent.mkdir(parents=True)
    zshrc.write_text("# mine\nalias ll='ls -l'\n")
    apply("zsh", defaults(zsh={"plugins": ["git", "sudo"], "extras": ["zsh-syntax-highlighting"]}))
    assert [c[:5] for c in machine.calls if c[0] == "git"] == [CLONE]
    assert home(".config/zsh/dotfiles.zsh").read_text().splitlines()[3:] == [
        'export ZSH="$HOME/.oh-my-zsh"',
        'ZSH_THEME="robbyrussell"',
        "plugins=(git sudo)",
        'source "$ZSH/oh-my-zsh.sh"',
        "# Last: it wraps the widgets defined before it.",
        "source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh",
    ]
    # At the top: what is there already comes after, and overrides it.
    assert zshrc.read_text() == "source ~/.config/zsh/dotfiles.zsh\n# mine\nalias ll='ls -l'\n"
    assert ["chsh", "-s", "/usr/bin/zsh", "u"] in machine.calls
    out, err = capsys.readouterr()
    assert "-> login shell of u: /usr/bin/zsh (was /bin/bash)\n" in out
    assert "log out and back in" in err
    (home(".oh-my-zsh") / "oh-my-zsh.sh").touch()
    login_shell(monkeypatch, "/bin/zsh")
    machine.calls.clear()
    apply("zsh", defaults(zsh={"plugins": ["git", "sudo"], "extras": ["zsh-syntax-highlighting"]}))
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_zsh_creates_zshrc_with_the_source_line(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    apply("zsh")
    assert home(".zshrc").read_text() == "source ~/.config/zsh/dotfiles.zsh\n"
    text = home(".config/zsh/dotfiles.zsh").read_text()
    assert "zsh-autosuggestions.zsh" in text and "zsh-syntax-highlighting.zsh" in text
    assert "p10k" not in text
    assert not home(".p10k.zsh").exists()


P10K_REPO = "https://github.com/romkatv/powerlevel10k.git"
P10K = {"theme": {"name": "powerlevel10k/powerlevel10k", "repo": P10K_REPO}}


def omz_cloned() -> None:
    home(".oh-my-zsh").mkdir(parents=True)
    (home(".oh-my-zsh") / "oh-my-zsh.sh").touch()


def theme_clone(machine, url: str, branch: str) -> list[str]:
    """powerlevel10k's clone made, as git reports it: URL, on BRANCH."""
    theme = home(".oh-my-zsh/custom/themes/powerlevel10k")
    (theme / ".git").mkdir(parents=True, exist_ok=True)
    git = ("git", "-C", str(theme))
    machine.answers[(*git, "remote", "get-url", "origin")] = (0, url)
    machine.answers[(*git, "rev-parse", "--abbrev-ref", "HEAD")] = (0, branch)
    return [*CLONE, url, str(theme)]


def test_zsh_theme_from_its_repo_with_p10k_settings(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    apply("zsh", defaults(zsh=P10K))
    theme = home(".oh-my-zsh/custom/themes/powerlevel10k")
    assert [c for c in machine.calls if c[:2] == ["git", "clone"]] == [
        [*CLONE, P10K_REPO, str(theme)]
    ]
    assert home(".p10k.zsh").read_text() == (Layout().home / ".p10k.zsh").read_text()
    text = home(".config/zsh/dotfiles.zsh").read_text()
    # Instant prompt before oh-my-zsh, the settings after it.
    assert text.index("p10k-instant-prompt") < text.index('ZSH_THEME="powerlevel10k/powerlevel10k"')
    assert text.index('source "$ZSH/oh-my-zsh.sh"') < text.index("source ~/.p10k.zsh")
    theme_clone(machine, P10K_REPO, "master")
    capsys.readouterr()
    machine.calls.clear()
    apply("zsh", defaults(zsh=P10K))
    assert capsys.readouterr().out == ""
    assert not [c for c in machine.calls if c[:2] == ["git", "clone"]]


def test_zsh_theme_on_another_branch_or_repo_is_cloned_again(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    clone = theme_clone(machine, P10K_REPO, "master")
    on_dev = defaults(zsh={"theme": {**P10K["theme"], "branch": "dev"}})
    apply("zsh", on_dev)
    assert [c for c in machine.calls if c[:2] == ["git", "clone"]] == [
        [*clone[:-2], "--branch", "dev", *clone[-2:]]
    ]
    assert "-> theme powerlevel10k cloned into " in capsys.readouterr().out
    theme_clone(machine, P10K_REPO, "dev")
    machine.calls.clear()
    apply("zsh", on_dev)
    assert not [c for c in machine.calls if c[:2] == ["git", "clone"]]
    theme_clone(machine, "https://example.org/fork.git", "dev")
    apply("zsh", on_dev)
    assert [c for c in machine.calls if c[:2] == ["git", "clone"]]


def test_zsh_built_in_theme_clones_no_theme(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    apply("zsh", defaults(zsh={"theme": {"name": "agnoster"}}))
    assert not [c for c in machine.calls if c[0] == "git"]
    assert 'ZSH_THEME="agnoster"' in home(".config/zsh/dotfiles.zsh").read_text()


def test_zsh_theme_of_a_repo_needs_its_dir(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    with pytest.raises(engine.Failed, match="must be <dir>/<name>"):
        apply("zsh", defaults(zsh={"theme": {"name": "p10k", "repo": P10K_REPO}}))


def test_zsh_dry_run_clones_nothing(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    leftover = home(".oh-my-zsh/half")
    leftover.mkdir(parents=True)
    engine.current().dry_run = True
    apply("zsh")
    assert machine.calls == []
    assert leftover.exists()
    assert "-> oh-my-zsh cloned into " in capsys.readouterr().out
