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
    fonts = classes(ArchLinuxOs)["fonts"](cfg["features"]["fonts"], None)
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
