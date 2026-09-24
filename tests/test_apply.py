import subprocess
import sys
import tomllib
from pathlib import Path
from typing import ClassVar

import pytest

from dotfiles import apply as runner
from dotfiles import engine, platforms
from dotfiles.apply import Step, apply, order, steps
from dotfiles.config import ROOT, ConfigError
from dotfiles.feature import Feature
from dotfiles.platforms.linux import Linux

HEAD = "from dotfiles.engine import defer, die, notice\nfrom dotfiles.feature import Feature\n\n\n"


class FakeLinux(Linux):
    """A platform whose package manager is a set and a dict."""

    # Class-wide, so a test sets them before apply() creates the platform.
    installed: ClassVar[set[str]] = set()
    graph: ClassVar[dict[str, set[str]]] = {}  # package -> everything it needs
    installs: ClassVar[list[list[str]]] = []
    replaced: ClassVar[list[list[str]]] = []  # REPLACES of each install
    broken = False  # install fails

    def missing(self, names):
        return [n for n in names if n not in self.installed]

    def install(self, names, replaces=()):
        self.installs.append(names)
        self.replaced.append(list(replaces))
        if self.broken:
            raise RuntimeError("mirror down")
        self.installed.update(names)

    def depends(self, names):
        return {n: self.graph.get(n, set()) for n in names}


class FakeArch(FakeLinux):
    pass


FakeArch.__name__ = "Arch"


@pytest.fixture
def system(monkeypatch) -> type[FakeLinux]:
    monkeypatch.setattr(FakeLinux, "installed", set())
    monkeypatch.setattr(FakeLinux, "graph", {})
    monkeypatch.setattr(FakeLinux, "installs", [])
    monkeypatch.setattr(FakeLinux, "replaced", [])
    monkeypatch.setattr(FakeLinux, "broken", False)
    monkeypatch.setattr(runner.platforms, "detect", lambda cfg, package: FakeArch(cfg))
    return FakeLinux


def feature(
    cls: str,
    apply: str = "pass",
    packages: list[str] | None = None,
    on="Linux",
    replaces: list[str] | None = None,
) -> str:
    """A feature module: class CLS whose apply runs APPLY, supported on ON
    with PACKAGES, which replace REPLACES."""
    body = f"class {cls}(Feature):\n    def apply(self, strategy):\n        {apply}\n\n"
    body += f"    class {on}:\n"
    body += f"        def packages(self):\n            return {packages or []!r}\n"
    body += f"        def replaces(self):\n            return {replaces or []!r}\n"
    return body


def make_package(tmp_path, monkeypatch, modules: dict[str, str]) -> str:
    """A package of fake features, one module per entry."""
    pkg = tmp_path / "pkg" / "fakefeatures"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    for name, body in modules.items():
        (pkg / f"{name}.py").write_text(HEAD + body)
    monkeypatch.syspath_prepend(str(tmp_path / "pkg"))
    for name in [m for m in sys.modules if m.split(".")[0] == "fakefeatures"]:
        monkeypatch.delitem(sys.modules, name)  # each test imports its own package
    return "fakefeatures"


@pytest.fixture
def root(tmp_path) -> Path:
    root = tmp_path / "repo"
    (root / "hosts").mkdir(parents=True)
    (root / "dotfiles").mkdir()
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\non.enabled = true\noff.enabled = false\n"
    )
    (root / "hosts/h.toml").write_text("")
    return root


def test_gates_and_platforms(root, system, tmp_path, monkeypatch, capsys):
    package = make_package(
        tmp_path,
        monkeypatch,
        {
            "on": feature("On", 'print("on ran")'),
            "off": feature("Off", 'raise AssertionError("a disabled feature ran")'),
            "always": feature("Always", 'print("always ran")'),  # not in the schema
            "elsewhere": feature("Elsewhere", "die('ran')", on="Debian"),
            "archonly": feature(
                "ArchOnly", 'print("arch ran", type(strategy).__name__)', on="Arch"
            ),
        },
    )
    assert apply("h", root, package=package) == 0
    assert capsys.readouterr() == ("always ran\narch ran ArchOnly.Arch\non ran\n", "")


def test_the_strategy_is_the_platform_plus_the_nested_class(system):
    class Tool(Feature):
        def apply(self, strategy):
            return strategy.flag(), strategy.missing(["x"])

        class Linux:
            def flag(self):
                return "--linux"

        class Arch:
            def flag(self):
                return "--arch"

    tool = Tool({"k": 1})
    strategy = tool.strategy(FakeArch({"k": 1}))
    assert type(strategy).__name__ == "Tool.Arch" and strategy.cfg == {"k": 1}
    assert tool.apply(strategy) == ("--arch", ["x"])
    del Tool.Arch
    assert tool.apply(tool.strategy(FakeArch({}))) == ("--linux", ["x"])


def test_one_install_then_silence(root, system, tmp_path, monkeypatch, capsys):
    package = make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", packages=["postgres"]),
            "web": feature("Web", packages=["nginx", "git"]),
            "tools": feature("Tools", packages=["git"], replaces=["git-git"]),
        },
    )
    system.installed = {"nginx"}
    assert apply("h", root, package=package) == 0
    assert system.installs == [["git", "postgres"]]
    assert system.replaced == [["git-git"]]
    assert capsys.readouterr().out == "-> packages: git postgres (missing)\n"
    assert apply("h", root, package=package) == 0
    assert system.installs == [["git", "postgres"]]
    assert capsys.readouterr() == ("", "")


def test_dry_run_installs_nothing_and_runs_every_feature(
    root, system, tmp_path, monkeypatch, capsys
):
    package = make_package(tmp_path, monkeypatch, {"db": feature("Db", 'print("db")', ["pg"])})
    assert apply("h", root, dry_run=True, package=package) == 0
    assert system.installs == []
    assert capsys.readouterr().out == "-> packages: pg (missing)\ndb\n"


def step(name, packages=()):
    return Step(name, None, None, frozenset(packages), frozenset())


def test_order_follows_the_package_graph():
    steps_ = [
        step("web", ["php", "git"]),
        step("db", ["postgres"]),
        step("app", ["app"]),
        step("tools", ["git"]),
        step("zlib", []),
    ]
    graph = {"php": {"postgres", "git", "glibc"}, "app": {"php", "postgres"}, "git": {"glibc"}}
    got = [(s.name, after) for s, after in order(steps_, graph)]
    assert got == [
        ("db", []),
        ("tools", []),
        ("web", ["db"]),  # php needs postgres; git is web's own, so not after tools
        ("app", ["db", "web"]),
        ("zlib", []),
    ]


def test_order_breaks_a_cycle_by_name():
    graph = {"x": {"y"}, "y": {"x"}}
    got = [(s.name, after) for s, after in order([step("b", ["y"]), step("a", ["x"])], graph)]
    assert got == [("a", ["b"]), ("b", ["a"])]


def test_failures_block_what_builds_on_them(root, system, tmp_path, monkeypatch, capsys):
    package = make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", 'die("broken")', ["postgres"]),
            "web": feature("Web", 'print("web ran")', ["php"]),
            "app": feature("App", 'print("app ran")', ["app"]),
            "net": feature("Net", 'defer("cloning x failed")', ["curl"]),
            "note": feature("Note", 'notice("reboot")'),
            "crash": feature("Crash", "raise RuntimeError('bug')"),
            "z": feature("Z", 'print("z ran")', ["zsh"]),
        },
    )
    system.installed = {"postgres", "php", "app", "curl", "zsh"}
    system.graph = {"php": {"postgres"}, "app": {"php"}, "zsh": {"curl"}}
    assert apply("h", root, package=package) == 1
    out, err = capsys.readouterr()
    assert out == (
        "z ran\n"
        "\nNotices from this apply:\n"
        "    cloning x failed (network?) — the next apply retries\n"
        "    reboot\n"
    )
    assert err == (
        "error: crash: bug\n"
        "error: db: broken\n"
        "warning: cloning x failed (network?) — the next apply retries\n"
        "warning: reboot\n"
        "error: web: not run, db failed\n"
        "error: app: not run, web failed\n"
    )


def test_packages_that_did_not_install_block_their_features(
    root, system, tmp_path, monkeypatch, capsys
):
    package = make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", 'print("db ran")', ["postgres"]),
            "plain": feature("Plain", 'print("plain ran")'),
            "ok": feature("Ok", 'print("ok ran")', ["zsh"]),
        },
    )
    system.installed = {"zsh"}
    system.broken = True
    assert apply("h", root, package=package) == 1
    out, err = capsys.readouterr()
    assert out == "-> packages: postgres (missing)\nok ran\nplain ran\n"
    assert err == ("error: packages: mirror down\nerror: db: not run, packages missing: postgres\n")


def test_notices_survive_ctrl_c(root, system, tmp_path, monkeypatch, capsys):
    def interrupt(*args):
        raise KeyboardInterrupt

    package = make_package(tmp_path, monkeypatch, {"note": feature("Note", 'notice("reboot")')})
    monkeypatch.setattr(FakeArch, "setup", lambda self: engine.notice("reboot"))
    monkeypatch.setattr("dotfiles.apply._deploy", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply("h", root, package=package)
    assert capsys.readouterr().out.endswith("Notices from this apply:\n    reboot\n")


def test_a_module_defines_one_feature(root, system, tmp_path, monkeypatch):
    package = make_package(tmp_path, monkeypatch, {"two": feature("A") + feature("B")})
    with pytest.raises(ConfigError, match="^fakefeatures.two: defines 2 features, not one$"):
        steps({"features": {}}, FakeArch({}), package)


# Modules that always run, switched by a setting outside [features].
UNSWITCHED = {"ssh_key", "rbw"}
# Features without a module: Arch.setup() does them.
SETUP = {"pacman", "makepkg", "reflector"}
# Features of the batches still to come (SPEC-features); shrinks to nothing.
NOT_YET = {
    *("luks_discard", "nvidia", "plymouth", "snapper", "swap"),  # batch 4
    *("fnm", "libvirt", "rustup", "ssh_agent", "uv", "zsh"),  # batch 5
    *("firefox", "greetd", "niri", "vscode"),  # batches 6 and 7
}


def test_real_features_are_consistent():
    cfg = tomllib.loads((ROOT / "dotfiles/defaults.toml").read_text())
    for table in cfg["features"].values():
        table["enabled"] = True
    found = {s.name: s for s in steps(cfg, FakeArch(cfg))}
    for name, s in found.items():
        assert type(s.feature).__name__ == name.title().replace("_", ""), name
        assert name in cfg["features"] or name in UNSWITCHED, f"{name}: not in the schema"
    missing = set(cfg["features"]) - set(found) - SETUP - NOT_YET
    assert not missing, f"features without a module: {sorted(missing)}"


@pytest.fixture
def arch(monkeypatch):

    monkeypatch.setattr(platforms.platform, "freedesktop_os_release", lambda: {"ID": "arch"})


def test_nobeep(monkeypatch, capsys):
    from dotfiles.features.nobeep import Nobeep

    nobeep = Nobeep({})
    strategy = nobeep.strategy(FakeArch({}))
    assert type(strategy).__name__ == "Nobeep.Linux" and strategy.packages() == []
    monkeypatch.setattr(engine, "DRY_RUN", True)
    nobeep.apply(strategy)
    assert capsys.readouterr().out == "-> /etc/modprobe.d/nobeep.conf (missing)\n"
    assert not engine.SYSROOT.exists()

    # Tests never become root: the install that would set root:root is only recorded.
    monkeypatch.setattr(engine, "DRY_RUN", False)
    calls = []
    monkeypatch.setattr(engine, "_run", lambda argv, **kw: calls.append(argv))
    monkeypatch.setenv("SUDO_CMD", "")
    nobeep.apply(strategy)
    dst = str(engine.SYSROOT / "etc/modprobe.d/nobeep.conf")
    assert calls[0][:8] == ["install", "-D", "-m", "644", "-o", "root", "-g", "root"]
    assert calls[0][-1] == dst
    capsys.readouterr()

    conf = Path(dst)
    conf.parent.mkdir(parents=True)
    conf.write_text("blacklist pcspkr\n")
    conf.chmod(0o644)
    monkeypatch.setattr(engine, "_owner", lambda path: "root:root")
    nobeep.apply(strategy)
    assert capsys.readouterr().out == ""


def test_dry_run_on_a_real_host_never_calls_sudo(arch, monkeypatch, capsys):
    """hyper-lin end to end on the real Arch platform: checks only (which
    answer "nothing installed, nothing enabled"), nothing written, sudo
    untouched."""

    def checks_only(argv, check=False, **kwargs):
        if check:  # run(): a mutation
            pytest.fail(f"ran {argv}")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(engine, "_run", checks_only)
    assert apply("hyper-lin", dry_run=True) == 0
    out = capsys.readouterr().out
    assert "-> /etc/modprobe.d/nobeep.conf (missing)\n" in out
    assert "-> ~/.zshrc (missing)\n" in out
    assert not (Path.home() / ".zshrc").exists()


SESSION = """
from contextlib import contextmanager

LOG = []


class Snap(Feature):
    @contextmanager
    def session(self, system):
        LOG.append("enter")
        try:
            yield
        finally:
            LOG.append("exit")

    def apply(self, strategy):
        LOG.append("apply")
        die("broken")

    class Linux:
        pass
"""


def test_a_session_wraps_the_whole_apply(root, system, tmp_path, monkeypatch):
    package = make_package(tmp_path, monkeypatch, {"on": SESSION, "off": SESSION})
    monkeypatch.setattr(
        FakeArch, "setup", lambda self: sys.modules[f"{package}.on"].LOG.append("setup")
    )
    assert apply("h", root, package=package) == 1
    assert sys.modules[f"{package}.on"].LOG == ["enter", "setup", "apply", "exit"]
    assert f"{package}.off" not in sys.modules  # a disabled feature is not even imported
