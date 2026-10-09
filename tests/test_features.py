import os
import pwd
import subprocess
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from dotfiles import engine
from dotfiles.feature import Setting, classes, table
from dotfiles.layout import Layout
from dotfiles.platforms.arch import ArchLinuxOs
from dotfiles.platforms.arch._pacman import Pacman
from dotfiles.platforms.arch.features.packaging import _jobs
from dotfiles.platforms.debian import DebianOs
from dotfiles.platforms.linux.features.system.swap import _bytes, _shown
from dotfiles.platforms.void import VoidOs

# Each feature's full name by its leaf: swap -> system.swap, for the helpers below.
_NAMES = {
    name.rpartition(".")[2]: name for os in (ArchLinuxOs, DebianOs, VoidOs) for name in classes(os)
}


def defaults(**features) -> dict:
    """The schema's config with FEATURES' settings changed, by leaf name, tables merged."""
    cfg = tomllib.loads(Layout().defaults.read_text())
    for name, settings in features.items():
        for key, value in settings.items():
            found = table(cfg["features"], _NAMES[name])
            if isinstance(value, dict):
                found[key].update(value)
            else:
                found[key] = value
    return cfg


def apply(name: str, cfg: dict | None = None) -> None:
    """Arch's feature NAME, its leaf, applied with CFG."""
    cfg, name = cfg or defaults(), _NAMES[name]
    classes(ArchLinuxOs)[name](table(cfg["features"], name), ArchLinuxOs(engine.current())).apply()


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


def test_rustup_on_void_runs_rustup_init_once_then_its_rustup(machine, capsys):
    cfg = defaults(rustup={"toolchain": "beta"})
    rustup = home(".cargo/bin/rustup")  # under the sysroot; it runs as str(real)
    real = Path.home() / ".cargo/bin/rustup"
    classes(VoidOs)["development.rustup"](
        cfg["features"]["development"]["rustup"], VoidOs(engine.current())
    ).apply()
    assert machine.calls[0] == ["rustup-init", "-y", "--default-toolchain", "beta"]
    assert "-> rustup installed by rustup-init, default beta\n" in capsys.readouterr().out
    rustup.parent.mkdir(parents=True)
    rustup.touch(mode=0o755)
    machine.answers[(str(real), "default")] = (0, "beta-x86_64-unknown-linux-gnu (default)")
    machine.answers[(str(real), "show")] = RUSTUP_SHOW
    machine.calls.clear()
    classes(VoidOs)["development.rustup"](
        cfg["features"]["development"]["rustup"], VoidOs(engine.current())
    ).apply()
    assert [c[0] for c in machine.calls] == [str(real), str(real)]
    assert capsys.readouterr().out == ""


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


PKGFILE_UPDATE = ["pkgfile", "--update"]


def test_pkgfile_turns_the_timer_on_and_downloads_once(machine, capsys):
    apply("pkgfile")
    assert machine.calls[-2:] == [
        ["systemctl", "enable", "--now", "pkgfile-update.timer"],
        PKGFILE_UPDATE,
    ]
    assert capsys.readouterr().out.endswith("-> pkgfile's database downloaded\n")
    write("/var/cache/pkgfile/core.files", "")
    machine.answers.update(
        {
            ("systemctl", "is-enabled", "pkgfile-update.timer"): (0, "enabled"),
            ("systemctl", "is-active", "pkgfile-update.timer"): (0, "active"),
        }
    )
    machine.calls.clear()
    apply("pkgfile")
    assert capsys.readouterr().out == ""
    assert PKGFILE_UPDATE not in machine.calls


def test_pkgfile_failed_download_is_a_notice(machine, capsys):
    machine.answers[tuple(PKGFILE_UPDATE)] = (1, "")
    apply("pkgfile")
    out, err = capsys.readouterr()
    assert "database downloaded" not in out
    assert "downloading pkgfile's database failed (network?)" in err


NERD = "https://github.com/ryanoasis/nerd-fonts/releases/download"


def nerd_calls(machine) -> list[list[str]]:
    return [c[:2] for c in machine.calls if c[0] in ("curl", "tar", "fc-cache")]


def test_fonts_downloads_each_nerd_font_once_and_caches(machine, capsys):
    apply("fonts", defaults(fonts={"nerd_fonts": ["JetBrainsMono"]}))
    fonts = home(".local/share/fonts/nerd-fonts")
    curl = next(c for c in machine.calls if c[0] == "curl")
    assert curl[-1] == f"{NERD}/v3.5.1/JetBrainsMono.tar.xz"
    assert nerd_calls(machine) == [["curl", "-fsSL"], ["tar", "-xf"], ["fc-cache", str(fonts)]]
    assert (fonts / "JetBrainsMono/.source").read_text() == f"{curl[-1]}\n"
    assert f"-> Nerd Font JetBrainsMono from {curl[-1]}\n" in capsys.readouterr().out
    machine.calls.clear()
    apply("fonts", defaults(fonts={"nerd_fonts": ["JetBrainsMono"]}))
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_fonts_another_release_or_url_downloads_again(machine):
    apply("fonts", defaults(fonts={"nerd_fonts": ["JetBrainsMono"]}))
    for changed, url in [
        ({"nerd_version": "v3.6.0"}, f"{NERD}/v3.6.0/JetBrainsMono.tar.xz"),
        ({"nerd_url": "https://example.org/{name}.zst"}, "https://example.org/JetBrainsMono.zst"),
    ]:
        machine.calls.clear()
        apply("fonts", defaults(fonts={"nerd_fonts": ["JetBrainsMono"], **changed}))
        assert next(c for c in machine.calls if c[0] == "curl")[-1] == url


def test_fonts_dry_run_downloads_nothing(machine, capsys):
    engine.current().dry_run = True
    apply("fonts", defaults(fonts={"nerd_fonts": ["FiraCode"]}))
    assert nerd_calls(machine) == []
    assert not home(".local/share/fonts").exists()
    assert f"-> Nerd Font FiraCode from {NERD}/v3.5.1/FiraCode.tar.xz\n" in capsys.readouterr().out


def test_fonts_packages():
    cfg = defaults(fonts={"packages": ["noto-fonts-emoji"]})
    fonts = classes(ArchLinuxOs)["desktop.fonts"](cfg["features"]["desktop"]["fonts"], None)
    assert fonts.packages() == ["fontconfig", "noto-fonts-emoji"]
    fonts.settings["nerd_fonts"] = ["FiraCode"]
    assert fonts.packages() == ["fontconfig", "noto-fonts-emoji", "curl"]


def fontconfig() -> list[str]:
    text = home(".config/fontconfig/conf.d/50-dotfiles.conf").read_text()
    return [line.strip() for line in text.split("<fontconfig>")[1].splitlines() if line.strip()]


def test_fonts_writes_only_the_preferences_set(machine):
    apply("fonts")
    assert fontconfig() == ["</fontconfig>"]
    apply(
        "fonts",
        defaults(
            fonts={
                "default": {"monospace": "JetBrainsMono Nerd Font", "sans_serif": "Noto Sans"},
                "render": {"antialias": True, "hinting": "slight", "subpixel": "rgb"},
            }
        ),
    )
    assert fontconfig() == [
        "<alias>",
        "<family>monospace</family>",
        "<prefer><family>JetBrainsMono Nerd Font</family></prefer>",
        "</alias>",
        "<alias>",
        "<family>sans-serif</family>",
        "<prefer><family>Noto Sans</family></prefer>",
        "</alias>",
        '<match target="font">',
        '<edit name="antialias" mode="assign"><bool>true</bool></edit>',
        '<edit name="hinting" mode="assign"><bool>true</bool></edit>',
        '<edit name="hintstyle" mode="assign"><const>hintslight</const></edit>',
        '<edit name="rgba" mode="assign"><const>rgb</const></edit>',
        "</match>",
        "</fontconfig>",
    ]
    apply("fonts", defaults(fonts={"render": {"hinting": "none"}}))
    assert '<edit name="hinting" mode="assign"><bool>false</bool></edit>' in fontconfig()
    assert not any("hintstyle" in line for line in fontconfig())


def login_shell(monkeypatch, shell: str) -> None:
    """SHELL the login shell; /usr/bin/zsh there, and /bin a link to usr/bin, as on Arch."""
    me = SimpleNamespace(pw_name="u", pw_shell=shell)
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: me)
    zsh = engine.current().files.path("/usr/bin/zsh")
    if not zsh.exists():
        zsh.parent.mkdir(parents=True)
        zsh.touch(mode=0o755)
        engine.current().files.path("/bin").symlink_to("usr/bin")


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
        "# What other features add, e.g. command_not_found's hook.",
        'for f in ~/.config/zsh/dotfiles.d/*.zsh(N); do source "$f"; done',
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


def test_zsh_login_shell_is_the_one_set(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    shell = engine.current().files.path("/usr/local/bin/zsh")
    shell.parent.mkdir(parents=True)
    shell.touch(mode=0o755)
    apply("zsh", defaults(zsh={"shell": "/usr/local/bin/zsh"}))
    assert ["chsh", "-s", "/usr/local/bin/zsh", "u"] in machine.calls


@pytest.mark.parametrize("dry_run", [False, True])
def test_zsh_shell_that_is_not_there_fails_before_chsh(machine, monkeypatch, dry_run):
    login_shell(monkeypatch, "/bin/bash")
    engine.current().dry_run = dry_run
    with pytest.raises(engine.Failed, match="^shell /usr/bin/zhs does not exist or is not"):
        apply("zsh", defaults(zsh={"shell": "/usr/bin/zhs"}))
    assert not [c for c in machine.calls if c[0] == "chsh"]


def test_zsh_creates_zshrc_with_the_source_line(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    apply("zsh")
    assert home(".zshrc").read_text() == "source ~/.config/zsh/dotfiles.zsh\n"
    text = home(".config/zsh/dotfiles.zsh").read_text()
    # By default no plugin of oh-my-zsh's and no extra.
    assert "plugins=()\n" in text and "/usr/share/zsh/plugins" not in text


BASH_HOOK = "source /usr/share/doc/pkgfile/command-not-found.bash"


def test_command_not_found_for_bash_adds_its_line_to_bashrc_once(machine, capsys):
    bashrc = home(".bashrc")
    bashrc.parent.mkdir(parents=True, exist_ok=True)
    bashrc.write_text("# mine\nalias ll='ls -l'\n")
    cfg = defaults(command_not_found={"shells": ["bash"]})
    apply("command_not_found", cfg)
    # At the end: what bash reads before it is the user's.
    assert bashrc.read_text() == f"# mine\nalias ll='ls -l'\n{BASH_HOOK}\n"
    assert not home(".config/zsh/dotfiles.d/command-not-found.zsh").exists()
    capsys.readouterr()
    machine.calls.clear()
    apply("command_not_found", cfg)
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_command_not_found_for_both_shells_writes_both_hooks(machine):
    apply("command_not_found", defaults(command_not_found={"shells": ["zsh", "bash"]}))
    assert home(".config/zsh/dotfiles.d/command-not-found.zsh").exists()
    assert home(".bashrc").read_text() == f"{BASH_HOOK}\n"


@pytest.mark.parametrize(
    ("shells", "requires"),
    [
        (["zsh"], ["package_tools.pkgfile", "shell.zsh"]),
        (["bash"], ["package_tools.pkgfile"]),
        (["bash", "zsh"], ["package_tools.pkgfile", "shell.zsh"]),
    ],
)
def test_command_not_found_requires_zsh_only_for_zsh(shells, requires):
    cfg = defaults(command_not_found={"shells": shells})["features"]["shell"]["command_not_found"]
    assert classes(ArchLinuxOs)["shell.command_not_found"](cfg, None).requires() == requires


def test_command_not_found_writes_the_hook_zsh_sources(machine, capsys):
    apply("command_not_found")
    hook = home(".config/zsh/dotfiles.d/command-not-found.zsh")
    assert (
        hook.read_text().splitlines()[-1] == "source /usr/share/doc/pkgfile/command-not-found.zsh"
    )
    capsys.readouterr()
    machine.calls.clear()
    apply("command_not_found")
    assert capsys.readouterr().out == ""
    assert machine.calls == []


GIT_INCLUDE = "[include] path = dotfiles.gitconfig"


def test_git_writes_ours_and_includes_it_on_top_once(machine, capsys):
    config = home(".config/git/config")
    config.parent.mkdir(parents=True)
    config.write_text("[user]\n\temail = mine@example.org\n")
    apply("git", defaults(git={"name": "Jane Doe", "email": "jane@example.org"}))
    assert home(".config/git/dotfiles.gitconfig").read_text().splitlines()[3:] == [
        "[user]",
        '\tname = "Jane Doe"',
        "\temail = jane@example.org",
    ]
    # At the top: the user's own settings come after, and override ours.
    assert config.read_text() == f"{GIT_INCLUDE}\n[user]\n\temail = mine@example.org\n"
    capsys.readouterr()
    machine.calls.clear()
    apply("git", defaults(git={"name": "Jane Doe", "email": "jane@example.org"}))
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_git_with_nothing_set_writes_no_user(machine):
    apply("git")
    assert "[user]" not in home(".config/git/dotfiles.gitconfig").read_text()
    assert home(".config/git/config").read_text() == f"{GIT_INCLUDE}\n"


def test_zsh_on_debian_sources_the_extras_from_debians_paths(machine, monkeypatch):
    login_shell(monkeypatch, "/usr/bin/zsh")
    cfg = defaults(zsh={"extras": ["zsh-autosuggestions", "zsh-syntax-highlighting"]})
    classes(DebianOs)["shell.zsh"](
        cfg["features"]["shell"]["zsh"], DebianOs(engine.current())
    ).apply()
    sources = [
        line
        for line in home(".config/zsh/dotfiles.zsh").read_text().splitlines()
        if line.startswith("source /")
    ]
    assert sources == [
        "source /usr/share/zsh-autosuggestions/zsh-autosuggestions.zsh",
        "source /usr/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh",
    ]


THEME_REPO = "https://example.org/someone/mytheme.git"
THEMED = {"theme": {"name": "mytheme/mytheme", "repo": THEME_REPO}}


def omz_cloned() -> None:
    home(".oh-my-zsh").mkdir(parents=True)
    (home(".oh-my-zsh") / "oh-my-zsh.sh").touch()


def theme_clone(machine, url: str, branch: str) -> list[str]:
    """The theme's clone made, as git reports it: URL, on BRANCH."""
    theme = home(".oh-my-zsh/custom/themes/mytheme")
    (theme / ".git").mkdir(parents=True, exist_ok=True)
    git = ("git", "-C", str(theme))
    machine.answers[(*git, "remote", "get-url", "origin")] = (0, url)
    machine.answers[(*git, "rev-parse", "--abbrev-ref", "HEAD")] = (0, branch)
    return [*CLONE, url, str(theme)]


def test_zsh_theme_from_its_repo(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    apply("zsh", defaults(zsh=THEMED))
    theme = home(".oh-my-zsh/custom/themes/mytheme")
    assert [c for c in machine.calls if c[:2] == ["git", "clone"]] == [
        [*CLONE, THEME_REPO, str(theme)]
    ]
    text = home(".config/zsh/dotfiles.zsh").read_text()
    assert 'ZSH_THEME="mytheme/mytheme"' in text
    theme_clone(machine, THEME_REPO, "master")
    capsys.readouterr()
    machine.calls.clear()
    apply("zsh", defaults(zsh=THEMED))
    assert capsys.readouterr().out == ""
    assert not [c for c in machine.calls if c[:2] == ["git", "clone"]]


def test_zsh_theme_on_another_branch_or_repo_is_cloned_again(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    omz_cloned()
    clone = theme_clone(machine, THEME_REPO, "master")
    on_dev = defaults(zsh={"theme": {**THEMED["theme"], "branch": "dev"}})
    apply("zsh", on_dev)
    assert [c for c in machine.calls if c[:2] == ["git", "clone"]] == [
        [*clone[:-2], "--branch", "dev", *clone[-2:]]
    ]
    assert "-> theme mytheme cloned into " in capsys.readouterr().out
    theme_clone(machine, THEME_REPO, "dev")
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
        apply("zsh", defaults(zsh={"theme": {"name": "mytheme", "repo": THEME_REPO}}))


def test_zsh_dry_run_clones_nothing(machine, monkeypatch, capsys):
    login_shell(monkeypatch, "/usr/bin/zsh")
    leftover = home(".oh-my-zsh/half")
    leftover.mkdir(parents=True)
    engine.current().dry_run = True
    apply("zsh")
    assert machine.calls == []
    assert leftover.exists()
    assert "-> oh-my-zsh cloned into " in capsys.readouterr().out


VCONSOLE_SETUP = ["systemctl", "restart", "systemd-vconsole-setup.service"]


def zone(name: str) -> None:
    write(f"/usr/share/zoneinfo/{name}", "")


def test_locale_generates_writes_and_links_once(machine, capsys):
    write("/etc/locale.gen", "# en_US.UTF-8 UTF-8\n#ru_RU.UTF-8 UTF-8\n")
    zone("Europe/Kyiv")
    cfg = defaults(locale={"timezone": "Europe/Kyiv"})
    apply("locale", cfg)
    locale_gen = engine.current().files.path("/etc/locale.gen").read_text()
    assert locale_gen == "en_US.UTF-8 UTF-8\n#ru_RU.UTF-8 UTF-8\n"
    assert ["locale-gen"] in machine.calls
    assert settings("/etc/locale.conf") == ["LANG=en_US.UTF-8"]
    assert settings("/etc/vconsole.conf") == ["KEYMAP=us"]
    assert VCONSOLE_SETUP in machine.calls
    localtime = engine.current().files.path("/etc/localtime")
    assert os.readlink(localtime) == "/usr/share/zoneinfo/Europe/Kyiv"
    capsys.readouterr()
    machine.calls.clear()
    apply("locale", cfg)
    assert capsys.readouterr().out == ""
    assert machine.calls == []


def test_locale_console_font_writes_it_and_a_missing_one_is_a_notice(machine, capsys):
    zone("UTC")
    apply("locale", defaults(locale={"console": {"font": "ter-v20n"}}))
    assert settings("/etc/vconsole.conf") == ["KEYMAP=us", "FONT=ter-v20n"]
    assert "console font ter-v20n is not in /usr/share/kbd/consolefonts" in capsys.readouterr().err


def test_locale_without_a_console_is_no_error(machine):
    zone("UTC")
    machine.answers[tuple(VCONSOLE_SETUP)] = (1, "")
    apply("locale")
    assert settings("/etc/vconsole.conf") == ["KEYMAP=us"]


def test_locale_unknown_timezone_fails_before_any_change(machine):
    with pytest.raises(engine.Failed, match="Nowhere/Town: no such timezone"):
        apply("locale", defaults(locale={"timezone": "Nowhere/Town"}))
    assert not engine.current().files.path("/etc/locale.conf").exists()
    assert machine.calls == []


def test_locale_packages_are_the_console_fonts_on_arch_and_locales_on_debian():
    cfg = defaults(locale={"console": {"packages": ["terminus-font"]}})["features"]["system"][
        "locale"
    ]
    assert classes(ArchLinuxOs)["system.locale"](cfg, None).packages() == ["terminus-font"]
    assert classes(DebianOs)["system.locale"](cfg, None).packages() == ["locales"]


def test_locale_not_in_locale_gen_is_added_at_its_end(machine):
    write("/etc/locale.gen", "#en_US.UTF-8 UTF-8\n")
    zone("UTC")
    apply("locale", defaults(locale={"locales": ["en_US.UTF-8 UTF-8", "uk_UA.UTF-8 UTF-8"]}))
    locale_gen = engine.current().files.path("/etc/locale.gen").read_text()
    assert locale_gen == "en_US.UTF-8 UTF-8\nuk_UA.UTF-8 UTF-8\n"
    assert ["locale-gen"] in machine.calls


def test_locale_another_lang_rewrites_only_locale_conf(machine, capsys):
    write("/etc/locale.gen", "en_US.UTF-8 UTF-8\n")
    zone("UTC")
    apply("locale")
    capsys.readouterr()
    machine.calls.clear()
    apply("locale", defaults(locale={"lang": "C.UTF-8"}))
    assert settings("/etc/locale.conf") == ["LANG=C.UTF-8"]
    assert capsys.readouterr().out == "-> /etc/locale.conf (content differs)\n"
    assert [c for c in machine.calls if c[0] != "install"] == []


def test_locale_on_debian_writes_lang_where_debian_reads_it_and_no_console(machine, capsys):
    zone("UTC")
    cfg = defaults(locale={"console": {"font": "ter-v20n"}})
    classes(DebianOs)["system.locale"](
        cfg["features"]["system"]["locale"], DebianOs(engine.current())
    ).apply()
    assert settings("/etc/default/locale") == ["LANG=en_US.UTF-8"]
    assert not engine.current().files.path("/etc/vconsole.conf").exists()
    assert VCONSOLE_SETUP not in machine.calls
    assert "features.system.locale.console is not applied on Debian" in capsys.readouterr().err


TIMESYNCD = ["systemctl", "enable", "--now", "systemd-timesyncd.service"]


def test_timesyncd_enables_the_service_once(machine, capsys):
    apply("timesyncd")
    assert machine.calls[-1] == TIMESYNCD
    assert "systemd-timesyncd.service enabled and started" in capsys.readouterr().out
    machine.answers.update(
        {
            ("systemctl", "is-enabled", "systemd-timesyncd.service"): (0, "enabled"),
            ("systemctl", "is-active", "systemd-timesyncd.service"): (0, "active"),
        }
    )
    machine.calls.clear()
    apply("timesyncd")
    assert capsys.readouterr().out == ""
    assert TIMESYNCD not in machine.calls


def test_timesyncd_is_part_of_systemd_on_arch_and_its_own_package_on_debian():
    cfg = defaults()["features"]["system"]["timesyncd"]
    assert classes(ArchLinuxOs)["system.timesyncd"](cfg, None).packages() == []
    assert classes(DebianOs)["system.timesyncd"](cfg, None).packages() == ["systemd-timesyncd"]


SWAP_DISK = {
    ("findmnt", "-no", "FSTYPE", "/"): (0, "btrfs"),
    ("findmnt", "-no", "UUID", "/"): (0, "0a1b-2c3d"),
    ("findmnt", "-no", "SOURCE", "/"): (0, "/dev/vda2[/@]"),
    ("btrfs", "subvolume", "list", "/"): (0, "ID 256 gen 9 top level 5 path @\n"),
}
SWAP_UNITS = ("swap.mount", "swap-swapfile.swap")


def test_swap_creates_the_subvolume_units_and_file_once(machine, capsys):
    machine.answers.update(SWAP_DISK)
    apply("swap", defaults(swap={"size": "4g"}))
    assert "What=UUID=0a1b-2c3d" in settings("/etc/systemd/system/swap.mount")
    assert "Options=noatime,subvol=/@swap" in settings("/etc/systemd/system/swap.mount")
    unit = settings("/etc/systemd/system/swap-swapfile.swap")
    assert "What=/swap/swapfile" in unit
    assert not any(line.startswith("Priority=") for line in unit)  # the kernel's: below zram
    calls = [" ".join(call) for call in machine.calls]
    assert any(c.startswith("mount -o subvolid=5 /dev/vda2 ") for c in calls)
    assert any(c.startswith("btrfs subvolume create ") and c.endswith("/@swap") for c in calls)
    swapfile = engine.current().files.path("/swap/swapfile")
    assert f"btrfs filesystem mkswapfile --size 4g {swapfile}" in calls
    assert "systemctl daemon-reload" in calls
    for unit in SWAP_UNITS:
        assert f"systemctl enable --now {unit}" in calls
    assert "-> created /swap/swapfile (4g)" in capsys.readouterr().out
    swapfile.parent.mkdir()
    swapfile.touch()
    os.truncate(swapfile, 4 * 1024**3)  # what mkswapfile made; sparse here
    for unit in SWAP_UNITS:
        machine.answers[("systemctl", "is-enabled", unit)] = (0, "enabled")
        machine.answers[("systemctl", "is-active", unit)] = (0, "active")
    machine.calls.clear()
    apply("swap", defaults(swap={"size": "4g"}))
    assert capsys.readouterr().out == ""
    assert [c for c in machine.calls if c[0] not in ("findmnt", "systemctl")] == []
    assert [c for c in machine.calls if c[:2] == ["systemctl", "enable"]] == []


def test_swap_keeps_an_existing_subvolume(machine):
    machine.answers.update(SWAP_DISK)
    machine.answers[("btrfs", "subvolume", "list", "/")] = (
        0,
        "ID 257 gen 9 top level 5 path @swap\n",
    )
    apply("swap", defaults(swap={"size": "4g"}))
    assert not any(c[:3] == ["btrfs", "subvolume", "create"] for c in machine.calls)


@pytest.mark.parametrize(
    ("fstype", "size", "error"),
    [
        ("btrfs", "", "features.system.swap.size is empty"),
        ("ext4", "4g", "/ is ext4: the swap file lives on a btrfs subvolume"),
    ],
)
def test_swap_fails_before_any_change(machine, fstype, size, error):
    machine.answers[("findmnt", "-no", "FSTYPE", "/")] = (0, fstype)
    with pytest.raises(engine.Failed, match=error):
        apply("swap", defaults(swap={"size": size}))
    assert not engine.current().files.path("/etc/systemd/system/swap.mount").exists()


def test_swap_line_left_in_fstab_is_a_notice(machine, capsys):
    machine.answers.update(SWAP_DISK)
    write("/etc/fstab", "UUID=0a1b-2c3d /swap btrfs subvol=/@swap 0 0\n")
    apply("swap", defaults(swap={"size": "4g"}))
    assert "/etc/fstab still has a line for /swap" in capsys.readouterr().err


def test_swap_dry_run_lists_no_subvolume(machine, capsys):
    machine.answers.update(SWAP_DISK)
    engine.current().dry_run = True
    apply("swap", defaults(swap={"size": "4g"}))
    assert "-> subvolume @swap, unless it is there (listing needs root)" in capsys.readouterr().out
    assert not any(c[:2] == ["btrfs", "subvolume"] for c in machine.calls)


def test_swap_needs_btrfs_progs():
    cfg = defaults()["features"]["system"]["swap"]
    assert classes(ArchLinuxOs)["system.swap"](cfg, None).packages() == ["btrfs-progs"]
    assert classes(DebianOs)["system.swap"](cfg, None).packages() == ["btrfs-progs"]


def swap_in_use(machine, capsys, size: str, have: int | None = None) -> Path:
    """A swap file of HAVE bytes (SIZE's), made with SIZE, its units on: swap already ran."""
    machine.answers.update(SWAP_DISK)
    for unit in SWAP_UNITS:
        machine.answers[("systemctl", "is-enabled", unit)] = (0, "enabled")
        machine.answers[("systemctl", "is-active", unit)] = (0, "active")
    swapfile = engine.current().files.path("/swap/swapfile")
    swapfile.parent.mkdir(parents=True)
    swapfile.touch()
    os.truncate(swapfile, _bytes(size) if have is None else have)  # sparse: no disk used
    apply("swap", defaults(swap={"size": size}))
    capsys.readouterr()
    machine.calls.clear()
    return swapfile


def swap_mutations(machine) -> list[list[str]]:
    return [
        c
        for c in machine.calls
        if c[0] != "findmnt" and c[1:2] not in (["is-enabled"], ["is-active"])
    ]


@pytest.mark.parametrize(
    ("size", "n"), [("4096", 4096), ("1k", 1024), ("2G", 2 * 1024**3), ("1t", 1024**4)]
)
def test_swap_size_in_bytes(size, n):
    assert _bytes(size) == n


@pytest.mark.parametrize(
    ("n", "shown"),
    [(2 * 1024**3, "2g"), (1536 * 1024**2, "1536m"), (1024**4, "1t"), (1000, "1000")],
)
def test_swap_size_shown_in_its_largest_whole_unit(n, shown):
    assert _shown(n) == shown


def test_swap_file_within_a_page_of_the_size_is_left_alone(machine, capsys):
    page = os.sysconf("SC_PAGE_SIZE")
    swap_in_use(machine, capsys, str(page + 1), have=page)  # mkswapfile makes whole pages
    apply("swap", defaults(swap={"size": str(page + 1)}))
    assert capsys.readouterr().out == ""
    assert swap_mutations(machine) == []


def test_swap_file_recreated_is_turned_on_again(machine, capsys):
    swap_in_use(machine, capsys, "2g")
    machine.answers[("systemctl", "is-active", "swap-swapfile.swap")] = (3, "inactive")  # stopped
    apply("swap", defaults(swap={"size": "4g"}))
    assert swap_mutations(machine)[-1] == ["systemctl", "start", "swap-swapfile.swap"]


def test_swap_file_mkswapfile_failing_after_rm_fails_the_feature(machine, capsys):
    swapfile = swap_in_use(machine, capsys, "2g")
    mkswapfile = ("btrfs", "filesystem", "mkswapfile", "--size", "4g", str(swapfile))
    machine.answers[mkswapfile] = (1, "")  # no room for 4g
    with pytest.raises(subprocess.CalledProcessError):
        apply("swap", defaults(swap={"size": "4g"}))
    # Swap stays off, no file: the next apply creates one, as on a new host.
    assert swap_mutations(machine)[-2:] == [["rm", "-f", str(swapfile)], list(mkswapfile)]
    assert "recreated" not in capsys.readouterr().out


def test_swap_file_of_the_size_set_is_left_alone(machine, capsys):
    swap_in_use(machine, capsys, "4g")
    apply("swap", defaults(swap={"size": "4g"}))
    assert capsys.readouterr().out == ""
    assert swap_mutations(machine) == []


def test_swap_file_of_another_size_is_recreated(machine, capsys):
    swapfile = swap_in_use(machine, capsys, "2g")
    apply("swap", defaults(swap={"size": "4g"}))
    assert swap_mutations(machine) == [
        ["systemctl", "stop", "swap-swapfile.swap"],
        ["rm", "-f", str(swapfile)],
        ["btrfs", "filesystem", "mkswapfile", "--size", "4g", str(swapfile)],
    ]
    assert "-> recreated /swap/swapfile (2g -> 4g)\n" in capsys.readouterr().out


def test_swap_file_kept_while_swapoff_fails_is_a_notice(machine, capsys):
    swap_in_use(machine, capsys, "2g")
    machine.answers[("systemctl", "stop", "swap-swapfile.swap")] = (1, "")
    apply("swap", defaults(swap={"size": "4g"}))
    assert swap_mutations(machine) == [["systemctl", "stop", "swap-swapfile.swap"]]
    out, err = capsys.readouterr()
    assert "recreated" not in out
    assert "/swap/swapfile is 2g, not 4g: swapoff failed" in err


def test_swap_file_recreated_in_a_dry_run_runs_nothing(machine, capsys):
    swap_in_use(machine, capsys, "2g")
    engine.current().dry_run = True
    apply("swap", defaults(swap={"size": "4g"}))
    assert "-> recreated /swap/swapfile (2g -> 4g)\n" in capsys.readouterr().out
    assert swap_mutations(machine) == []


ZRAM_UNIT = "systemd-zram-setup@zram0.service"


def test_zram_writes_its_config_and_restarts_only_on_a_change(machine, capsys):
    apply("zram")
    assert settings("/etc/systemd/zram-generator.conf") == [
        "[zram0]",
        "zram-size = min(ram / 2, 4096)",
        "compression-algorithm = zstd",
        "swap-priority = 100",
    ]
    reload = machine.calls.index(["systemctl", "daemon-reload"])
    assert machine.calls[reload + 1] == ["systemctl", "restart", ZRAM_UNIT]
    assert not engine.current().files.path("/etc/sysctl.d/99-dotfiles.conf").exists()
    capsys.readouterr()
    machine.answers.update(
        {
            ("systemctl", "is-enabled", ZRAM_UNIT): (0, "generated"),
            ("systemctl", "is-active", ZRAM_UNIT): (0, "active"),
        }
    )
    machine.calls.clear()
    apply("zram")
    assert capsys.readouterr().out == ""
    assert [c for c in machine.calls if c[1] not in ("is-enabled", "is-active")] == []


def test_zram_sets_the_sysctls_asked_for(machine):
    machine.answers[("sysctl", "-n", "vm.page-cluster")] = (0, "3")
    apply("zram", defaults(zram={"swappiness": 100, "watermark_scale_factor": 125}))
    assert settings("/etc/sysctl.d/99-dotfiles.conf") == [
        "vm.swappiness = 100",
        "vm.page-cluster = 0",
        "vm.watermark_scale_factor = 125",
    ]
    assert ["sysctl", "-qw", "vm.page-cluster=0"] in machine.calls


def test_zram_failed_restart_is_a_notice_and_the_sysctls_still_set(machine, capsys):
    machine.answers[("systemctl", "restart", ZRAM_UNIT)] = (1, "")  # swapoff of zram0 failed
    apply("zram", defaults(zram={"swappiness": 100}))
    assert "zram0 keeps its old settings until a reboot: restarting" in capsys.readouterr().err
    assert ["sysctl", "-qw", "vm.swappiness=100"] in machine.calls


def test_zram_generator_is_its_own_package():
    cfg = defaults()["features"]["system"]["zram"]
    assert classes(ArchLinuxOs)["system.zram"](cfg, None).packages() == ["zram-generator"]
    assert classes(DebianOs)["system.zram"](cfg, None).packages() == ["systemd-zram-generator"]


OOMD = "systemd-oomd.service"
OOMD_DROP_INS = {
    "/etc/systemd/oomd.conf.d/10-dotfiles.conf": [
        "[OOM]",
        "DefaultMemoryPressureLimit=60%",
        "DefaultMemoryPressureDurationSec=20s",
    ],
    "/etc/systemd/system/-.slice.d/10-oomd.conf": ["[Slice]", "ManagedOOMSwap=kill"],
    "/etc/systemd/system/user@.service.d/10-oomd.conf": [
        "[Service]",
        "ManagedOOMMemoryPressure=kill",
        "ManagedOOMMemoryPressureLimit=50%",
    ],
}


def test_oomd_writes_its_drop_ins_restarts_and_enables_once(machine, capsys):
    apply("oomd")
    for path, lines in OOMD_DROP_INS.items():
        assert settings(path) == lines
    calls = [
        c for c in machine.calls if c[0] == "systemctl" and c[1] not in ("is-enabled", "is-active")
    ]
    assert calls == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "try-restart", OOMD],  # oomd.conf.d is read when oomd starts
        ["systemctl", "enable", "--now", OOMD],
    ]
    capsys.readouterr()
    machine.answers.update(
        {
            ("systemctl", "is-enabled", OOMD): (0, "enabled"),
            ("systemctl", "is-active", OOMD): (0, "active"),
        }
    )
    machine.calls.clear()
    apply("oomd")
    assert capsys.readouterr().out == ""
    assert [c for c in machine.calls if c[1] not in ("is-enabled", "is-active")] == []


def test_oomd_is_part_of_systemd_on_arch_and_its_own_package_on_debian():
    cfg = defaults()["features"]["system"]["oomd"]
    assert classes(ArchLinuxOs)["system.oomd"](cfg, None).packages() == []
    assert classes(DebianOs)["system.oomd"](cfg, None).packages() == ["systemd-oomd"]


def test_packaging_runs_before_the_package_install():
    assert classes(ArchLinuxOs)["packaging"].before_packages


def _dkms():
    """Arch's system.dkms on the test machine."""
    return classes(ArchLinuxOs)["system.dkms"]({"enabled": True}, ArchLinuxOs(engine.current()))


def test_dkms_installs_the_headers_of_every_kernel():
    write("/usr/lib/modules/7.2.9-arch1-1/pkgbase", "linux\n")
    write("/usr/lib/modules/6.18.55-1-lts/pkgbase", "\nlinux-lts\n\n")
    write("/usr/lib/modules/6.1.0-extramodules/version", "")  # no pkgbase: not a kernel
    assert _dkms().packages() == ["dkms", "linux-headers", "linux-lts-headers"]
    assert classes(ArchLinuxOs)["system.dkms"].before_packages


def test_dkms_without_a_kernel_installs_dkms_alone_and_says_so():
    dkms = _dkms()
    assert dkms.packages() == ["dkms"]
    dkms.apply()
    assert any("no kernel" in n for n in engine.current().report.notices)


def _graphics(gpus, lib32=False, driver="current"):
    """Arch's hardware.graphics with GPUS, LIB32 and the NVIDIA DRIVER branch."""
    cfg = defaults(graphics={"gpus": gpus, "lib32": lib32, "nvidia": {"driver": driver}})
    settings = table(cfg["features"], "hardware.graphics")
    return classes(ArchLinuxOs)["hardware.graphics"](settings, ArchLinuxOs(engine.current()))


@pytest.mark.parametrize(
    ("gpus", "lib32", "driver", "packages"),
    [
        ([], True, "current", []),
        (["amd"], False, "current", ["mesa", "vulkan-radeon"]),
        (["amd"], True, "current", ["lib32-mesa", "lib32-vulkan-radeon", "mesa", "vulkan-radeon"]),
        (["intel"], False, "current", ["intel-media-driver", "mesa", "vulkan-intel"]),
        (
            ["nouveau"],
            True,
            "current",
            ["lib32-mesa", "lib32-vulkan-nouveau", "mesa", "vulkan-nouveau"],
        ),
        (["nvidia"], False, "current", ["libva-nvidia-driver", "nvidia-open-dkms", "nvidia-utils"]),
        (
            ["nvidia"],
            True,
            "580xx",
            [
                "lib32-nvidia-580xx-utils",
                "libva-nvidia-driver",
                "nvidia-580xx-dkms",
                "nvidia-580xx-utils",
            ],
        ),
        (["nvidia"], False, "390xx", ["nvidia-390xx-dkms", "nvidia-390xx-utils"]),
        (
            ["intel", "nvidia"],
            True,
            "current",
            [
                "intel-media-driver",
                "lib32-mesa",
                "lib32-nvidia-utils",
                "lib32-vulkan-intel",
                "libva-nvidia-driver",
                "mesa",
                "nvidia-open-dkms",
                "nvidia-utils",
                "vulkan-intel",
            ],
        ),
    ],
)
def test_graphics_packages(gpus, lib32, driver, packages):
    assert _graphics(gpus, lib32, driver).packages() == packages


def test_graphics_replaces_the_other_nvidia_branches():
    legacy = {
        b: [f"lib32-nvidia-{b}-utils", f"nvidia-{b}-dkms", f"nvidia-{b}-utils"]
        for b in ("390xx", "470xx", "580xx")
    }
    prebuilt = ["nvidia-open", "nvidia-open-lts"]  # conflict with nvidia-open-dkms
    assert _graphics(["nvidia"]).replaces() == sorted(
        prebuilt + [p for ps in legacy.values() for p in ps]
    )
    current = [
        "lib32-nvidia-utils",
        "nvidia-open",
        "nvidia-open-dkms",
        "nvidia-open-lts",
        "nvidia-utils",
    ]
    replaced = _graphics(["nvidia"], driver="580xx").replaces()
    assert replaced == sorted(current + legacy["390xx"] + legacy["470xx"])
    assert _graphics(["amd"]).replaces() == []


def test_graphics_requires_dkms_for_nvidia_and_multilib_for_lib32():
    multilib = Setting("packaging.pacman.multilib", True)
    assert _graphics(["amd"]).requires() == []
    assert _graphics(["nvidia"]).requires() == ["system.dkms"]
    assert _graphics(["amd"], lib32=True).requires() == [multilib]
    assert _graphics(["nvidia"], lib32=True).requires() == ["system.dkms", multilib]
    assert classes(ArchLinuxOs)["hardware.graphics"].before_packages
