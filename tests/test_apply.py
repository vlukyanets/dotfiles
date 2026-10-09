import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import ClassVar

import pytest

from dotfiles import apply as runner
from dotfiles import config, engine
from dotfiles.apply import apply
from dotfiles.errors import ConfigError
from dotfiles.feature import Setting, classes, table
from dotfiles.layout import Layout
from dotfiles.plan import Step, cycles, order, steps
from dotfiles.platforms import discovery
from dotfiles.platforms.arch import ArchLinuxOs
from dotfiles.platforms.debian import DebianOs
from dotfiles.platforms.linux import LinuxOs
from dotfiles.platforms.operating_system import OperatingSystem
from dotfiles.platforms.package_manager import PackageManager
from dotfiles.platforms.void import VoidOs

HEAD = "from dotfiles.engine import defer, die\nfrom dotfiles.feature import Feature, Setting\n\n\n"


class FakeManager(PackageManager):
    """A package manager that is a set and a dict."""

    # Class-wide, so a test sets them before apply() creates the platform.
    installed: ClassVar[set[str]] = set()
    graph: ClassVar[dict[str, set[str]]] = {}  # package -> everything it needs
    installs: ClassVar[list[list[str]]] = []
    replaced: ClassVar[list[list[str]]] = []  # REPLACES of each install
    aur: ClassVar[set[str]] = set()  # not in its repositories: left for build()
    builds: ClassVar[list[list[str]]] = []
    broken = False  # install fails

    def missing(self, names):
        return [n for n in names if n not in self.installed]

    def install(self, names, replaces=()):
        self.installs.append(names)
        self.replaced.append(list(replaces))
        if self.broken:
            raise RuntimeError("mirror down")
        self.installed.update(set(names) - self.aur)
        return [n for n in names if n in self.aur]

    def build(self, names):
        self.builds.append(names)
        self.installed.update(names)

    def upgrade(self):
        pass

    def depends(self, names):
        return {n: self.graph.get(n, set()) for n in names}

    def direct(self, names):
        return self.depends(names)


class FakeArch(OperatingSystem):  # not LinuxOs: no real feature of Linux's
    manager_class = FakeManager


FakeArch.__module__ = "fakeplat"  # its features: fakeplat/features/, from make_package


@pytest.fixture
def system(monkeypatch) -> type[FakeManager]:
    monkeypatch.setattr(FakeManager, "installed", set())
    monkeypatch.setattr(FakeManager, "graph", {})
    monkeypatch.setattr(FakeManager, "installs", [])
    monkeypatch.setattr(FakeManager, "replaced", [])
    monkeypatch.setattr(FakeManager, "aur", set())
    monkeypatch.setattr(FakeManager, "builds", [])
    monkeypatch.setattr(FakeManager, "broken", False)
    monkeypatch.setattr(discovery, "detect", lambda machine: FakeArch(machine))
    monkeypatch.setattr(discovery, "every", lambda machine: [FakeArch(machine)])
    return FakeManager


def feature(
    cls: str,
    apply: str = "pass",
    packages: list[str] | None = None,
    replaces: list[str] | None = None,
    requires: list | None = None,
) -> str:
    body = f"class {cls}(Feature):\n    def apply(self):\n        {apply}\n\n"
    body += f"    def packages(self):\n        return {packages or []!r}\n"
    body += f"    def replaces(self):\n        return {replaces or []!r}\n"
    body += f"    def requires(self):\n        return {requires or []!r}\n"
    return body


def make_package(tmp_path, monkeypatch, modules: dict[str, str], name: str = "fakeplat") -> None:
    """Platform package NAME with a module in features/ per entry: FakeArch's by default.

    An entry `group/name` is a module of a group, each group with its __init__.py;
    one ending in / is only the group.
    """
    pkg = tmp_path / "pkg" / name
    (pkg / "features").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "features/__init__.py").write_text("")
    for module, body in modules.items():
        *groups, leaf = module.split("/")
        where = pkg / "features"
        for group in groups:
            where /= group
            where.mkdir(exist_ok=True)
            (where / "__init__.py").write_text("")
        if leaf:
            (where / f"{leaf}.py").write_text(HEAD + body)
    monkeypatch.syspath_prepend(str(tmp_path / "pkg"))
    for loaded in [m for m in sys.modules if m.split(".")[0] == name]:
        monkeypatch.delitem(sys.modules, loaded)  # each test imports its own package


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
    make_package(
        tmp_path,
        monkeypatch,
        {
            "on": feature("On", 'print("on ran")'),
            "off": feature("Off", 'raise AssertionError("a disabled feature ran")'),
            "always": feature("Always", 'print("always ran")'),  # not in the schema
        },
    )
    assert apply("h", root) == 0
    # Fakes print directly, not through changed(): nothing counts as a change.
    out = "always ran\non ran\nnothing to change\n"
    assert capsys.readouterr() == (out, "")


def test_a_feature_without_enabled_always_runs(root, system, tmp_path, monkeypatch, capsys):
    (root / "dotfiles/defaults.toml").write_text("[features.kept]\nx = 1\n")
    make_package(tmp_path, monkeypatch, {"kept": feature("Kept", 'print("kept ran")')})
    assert apply("h", root) == 0
    assert capsys.readouterr().out == "kept ran\nnothing to change\n"
    (root / "hosts/h.toml").write_text("[features.kept]\nenabled = false\n")
    with pytest.raises(ConfigError, match=r"^hosts/h\.toml: features\.kept\.enabled: unknown key$"):
        config.resolve("h", root)


class _Base(LinuxOs):
    pass


class _Own(_Base):
    manager_class = FakeManager


_Base.__module__, _Own.__module__ = "fakebase", "fakeplat"


def test_a_platform_falls_back_to_its_base_for_what_it_lacks(tmp_path, monkeypatch):
    base = {
        "tool": feature("Tool", "return 'base'"),
        "base": feature("Base"),
        "g/x": feature("X", "return 'base x'"),
    }
    make_package(tmp_path, monkeypatch, base, name="fakebase")
    own = "from fakebase.features import tool\n\n\nclass Tool(tool.Tool):\n"
    own += "    def apply(self):\n        return 'own'\n"
    make_package(tmp_path, monkeypatch, {"tool": own})
    found = classes(_Own)
    assert found["tool"].__module__ == "fakeplat.features.tool"
    assert found["base"].__module__ == "fakebase.features.base"
    assert found["g.x"].__module__ == "fakebase.features.g.x"
    tool = found["tool"]({"k": 1}, _Own(engine.current()))
    assert tool.apply() == "own" and tool.settings == {"k": 1}
    assert tool.system.manager.missing(["x"]) == ["x"]
    assert classes(_Base)["tool"]({}, None).apply() == "base"


def test_a_feature_in_a_group_is_named_by_its_path(tmp_path, monkeypatch):
    make_package(
        tmp_path,
        monkeypatch,
        {
            "top": feature("Top"),
            "system/zram": feature("Zram"),
            "a/b/deep": feature("Deep"),
            "apps/system": feature("System"),  # a leaf named like a group
            "system/_helper": "X = 1\n",
            "_private/hidden": feature("Hidden"),
            "empty/": "",
        },
    )
    found = classes(FakeArch)
    assert sorted(found) == ["a.b.deep", "apps.system", "system.zram", "top"]
    assert found["system.zram"].__module__ == "fakeplat.features.system.zram"


def test_an_override_must_subclass_its_base(tmp_path, monkeypatch):
    make_package(tmp_path, monkeypatch, {"g/tool": feature("Tool")}, name="fakebase")
    make_package(tmp_path, monkeypatch, {"g/tool": feature("Tool")})  # a copy, not a subclass
    msg = r"^fakeplat/features/g/tool\.py: Tool must subclass fakebase's Tool$"
    with pytest.raises(ConfigError, match=msg):
        classes(_Own)


def test_a_feature_in_a_group_is_gated_by_its_table(root, system, tmp_path, monkeypatch, capsys):
    (root / "dotfiles/defaults.toml").write_text(
        "[features.g.on]\nenabled = true\n[features.g.off]\nenabled = false\n"
        "[features.h.need]\nenabled = true\n"
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "g/on": feature("On", 'print("on ran")'),
            "g/off": feature("Off", 'raise AssertionError("a disabled feature ran")'),
            "h/need": feature("Need", 'print("need ran")', requires=["g.on"]),
        },
    )
    assert apply("h", root) == 0
    assert capsys.readouterr().out == "on ran\nneed ran\nnothing to change\n"
    (root / "hosts/h.toml").write_text("[features.g.on]\nenabled = false\n")
    with pytest.raises(ConfigError, match=r"^h\.need: requires features\.g\.on\.enabled = true$"):
        apply("h", root)


def test_one_install_then_silence(root, system, tmp_path, monkeypatch, capsys):
    make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", packages=["postgres"]),
            "web": feature("Web", packages=["nginx", "git"]),
            "tools": feature("Tools", packages=["git"], replaces=["git-git"]),
        },
    )
    system.installed = {"nginx"}
    assert apply("h", root) == 0
    assert system.installs == [["git", "postgres"]]
    assert system.replaced == [["git-git"]]
    assert capsys.readouterr().out == "-> packages: git postgres (missing)\n"
    assert apply("h", root) == 0
    assert system.installs == [["git", "postgres"]]
    assert capsys.readouterr() == ("nothing to change\n", "")


def test_an_aur_package_is_built_at_its_feature_s_turn(root, system, tmp_path, monkeypatch, capsys):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\n" + "".join(f"{n}.enabled = true\n" for n in ("base", "app"))
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "base": feature(
                "Base", "self.system.report.changed(str(self.system.manager.installed))"
            ),
            "app": feature("App", packages=["git", "app-bin"], requires=["base"]),
        },
    )
    system.aur = {"app-bin"}
    assert apply("h", root) == 0
    assert system.installs == [["app-bin", "git"]]
    assert system.builds == [["app-bin"]]
    # base ran before app's AUR package was built
    assert capsys.readouterr().out == "-> packages: app-bin git (missing)\n-> {'git'}\n"
    assert apply("h", root) == 0
    assert system.builds == [["app-bin"]]


def test_dry_run_leaves_features_whose_packages_are_missing(
    root, system, tmp_path, monkeypatch, capsys
):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\n" + "".join(f"{n}.enabled = true\n" for n in ("db", "app", "shell"))
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", 'die("checked what is not there")', ["pg"]),
            "app": feature("App", 'die("ran")', requires=["db"]),
            "shell": feature("Shell", 'print("shell")', ["zsh"]),
        },
    )
    system.installed = {"zsh"}
    assert apply("h", root, dry_run=True) == 0
    assert system.installs == []
    assert capsys.readouterr() == (
        "-> packages: pg (missing)\n"
        + "-> db (after its packages)\n-> app (after its packages)\nshell\n",
        "",
    )


def step(name, packages=(), requires=()):
    return Step(name, None, frozenset(packages), frozenset(), frozenset(requires))


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


def test_order_puts_a_requirement_first():
    # No package ties them; "a" still runs after "b", which it requires.
    steps_ = [step("a", ["x"], requires=["b", "setup"]), step("b", ["y"]), step("c", ["z"])]
    got = [(s.name, after) for s, after in order(steps_, {})]
    assert got == [("b", []), ("a", ["b"]), ("c", [])]  # setup is no step: nothing to wait for


def test_order_follows_what_packages_provide():
    steps_ = [step("app", ["app"]), step("jdk", ["jdk-openjdk"])]
    graph = {"app": {"java-runtime"}}
    provides = {"jdk-openjdk": {"java-runtime"}, "app": {"app-bin"}}
    got = [(s.name, after) for s, after in order(steps_, graph, provides)]
    assert got == [("jdk", []), ("app", ["jdk"])]


def test_order_breaks_a_cycle_by_name():
    graph = {"x": {"y"}, "y": {"x"}}
    got = [(s.name, after) for s, after in order([step("b", ["y"]), step("a", ["x"])], graph)]
    assert got == [("a", ["b"]), ("b", ["a"])]  # every step has a place; apply runs neither


def test_cycles_each_once_from_the_first_name():
    edges = {"c": {"a"}, "a": {"b", "x"}, "b": {"c"}, "d": {"a", "d"}, "e": {"b"}}
    assert cycles(edges) == [["a", "b", "c"], ["d"]]  # x is no key: it needs nothing
    assert cycles({"a": {"b"}, "b": set()}) == []


def test_a_requires_cycle_is_a_config_error(root, system, tmp_path, monkeypatch):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\ngaming.enabled = true\nnvidia.enabled = true\npacman.enabled = true\n"
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "gaming": feature("Gaming", "die('ran')", requires=["nvidia", "pacman"]),
            "nvidia": feature("Nvidia", "die('ran')", requires=["gaming"]),
            "pacman": feature("Pacman", "die('ran')"),
        },
    )
    msg = "^gaming → nvidia → gaming: each requires the next, so none can run first$"
    with pytest.raises(ConfigError, match=msg):
        apply("h", root)
    assert system.installs == []  # found before any change
    cfg = {"features": {n: {"enabled": True} for n in ("gaming", "nvidia", "pacman")}}
    with pytest.raises(ConfigError, match=msg):
        runner.requirements(cfg)


def test_features_whose_packages_need_each_other_do_not_run(
    root, system, tmp_path, monkeypatch, capsys
):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\n"
        + "".join(f"{n}.enabled = true\n" for n in ("graphics", "glvnd", "game", "shell"))
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "graphics": feature("Graphics", 'print("graphics ran")', ["mesa"]),
            "glvnd": feature("Glvnd", 'print("glvnd ran")', ["libglvnd"]),
            "game": feature("Game", 'print("game ran")', ["steam"]),
            "shell": feature("Shell", 'print("shell ran")', ["zsh"]),
        },
    )
    system.installed = {"mesa", "libglvnd", "steam", "zsh"}
    system.graph = {"mesa": {"libglvnd"}, "libglvnd": {"mesa"}, "steam": {"mesa", "libglvnd"}}
    assert apply("h", root) == 1
    assert capsys.readouterr() == (
        "shell ran\n",
        (
            "error: glvnd, graphics: not run, they need each other: glvnd → graphics → glvnd\n"
            "error: game: not run, glvnd, graphics failed\n"
        ),
    )


def test_a_failure_alone_is_not_nothing_to_change(root, system, tmp_path, monkeypatch, capsys):
    make_package(tmp_path, monkeypatch, {"on": feature("On", 'die("broken")')})
    assert apply("h", root) == 1
    assert capsys.readouterr() == ("", "error: on: broken\n")


def test_errors_say_what_went_wrong_and_where(root, system, tmp_path, monkeypatch, capsys):
    make_package(
        tmp_path,
        monkeypatch,
        {
            "on": feature("On", 'self.settings["nope"]'),
            "cmd": feature("Cmd", 'self.system.shell.run("false")'),
            "div": feature("Div", "1 / 0"),
        },
    )
    assert apply("h", root) == 1
    err = capsys.readouterr().err.splitlines()
    assert [line.split(", at ")[0] for line in err] == [
        "error: cmd: `false` failed with exit status 1",
        "error: div: unexpected ZeroDivisionError (division by zero)",
        "error: on: features.on.nope: no such key in dotfiles/defaults.toml",
    ]
    # The line of the feature, not engine.run's.
    assert [line.split(", at ")[1].split("fakeplat/features/")[1] for line in err] == [
        'cmd.py:7: self.system.shell.run("false")',
        "div.py:7: 1 / 0",
        'on.py:7: self.settings["nope"]',
    ]


def test_failures_block_what_builds_on_them(root, system, tmp_path, monkeypatch, capsys):
    make_package(
        tmp_path,
        monkeypatch,
        {
            "db": feature("Db", 'die("broken")', ["postgres"]),
            "web": feature("Web", 'print("web ran")', ["php"]),
            "app": feature("App", 'print("app ran")', ["app"]),
            "net": feature("Net", 'defer("cloning x failed")', ["curl"]),
            "note": feature("Note", 'self.system.report.notice("reboot")'),
            "crash": feature("Crash", "raise RuntimeError('bug')"),
            "z": feature("Z", 'print("z ran")', ["zsh"]),
        },
    )
    system.installed = {"postgres", "php", "app", "curl", "zsh"}
    system.graph = {"php": {"postgres"}, "app": {"php"}, "zsh": {"curl"}}
    assert apply("h", root) == 1
    out, err = capsys.readouterr()
    assert out == (
        "z ran\n"
        "\nNotices from this apply:\n"
        "    cloning x failed (network?) — the next apply retries\n"
        "    reboot\n"
    )
    crash, err = err.split("\n", 1)
    assert crash.startswith("error: crash: unexpected RuntimeError (bug), at ")
    assert crash.endswith("fakeplat/features/crash.py:7: raise RuntimeError('bug')")
    assert err == (
        "error: db: broken\n"
        "warning: cloning x failed (network?) — the next apply retries\n"
        "warning: reboot\n"
        "error: web: not run, db failed\n"
        "error: app: not run, web failed\n"
    )


def test_a_failed_requirement_blocks(root, system, tmp_path, monkeypatch, capsys):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\nshell.enabled = true\nbar.enabled = true\n"
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "shell": feature("Shell", 'die("broken")'),
            "bar": feature("Bar", 'print("bar ran")', requires=["shell"]),
        },
    )
    assert apply("h", root) == 1
    assert capsys.readouterr() == ("", "error: shell: broken\nerror: bar: not run, shell failed\n")


def test_a_requirement_left_off_is_a_config_error(root, system, tmp_path, monkeypatch):
    (root / "dotfiles/defaults.toml").write_text(
        "[features]\non.enabled = true\noff.enabled = false\nelse.enabled = true\n"
    )
    make_package(
        tmp_path,
        monkeypatch,
        {
            "on": feature("On", "die('ran')", requires=["off", "nope"]),
            "off": feature("Off"),
        },
    )
    msg = "^on: requires nope, which is not a feature; on: requires features.off.enabled = true$"
    with pytest.raises(ConfigError, match=msg):
        apply("h", root)
    cfg = {"features": {"on": {"enabled": True}, "off": {"enabled": False}}}
    with pytest.raises(ConfigError, match=msg):
        runner.requirements(cfg)
    cfg["features"]["off"]["enabled"] = True
    with pytest.raises(ConfigError, match="^on: requires nope, which is not a feature$"):
        runner.requirements(cfg)


_SETTINGS_SCHEMA = """\
[features.own]
flag = false
name = "x"
[features.own.sub]
on = true
[features.g.need]
enabled = true
[features.off]
enabled = false
flag = true
"""


def _with_a_setting(root, tmp_path, monkeypatch, own_apply, own_requires, need_requires):
    """Features own (no enabled; unset: a boolean with no default), g.need and off."""
    (root / "dotfiles/defaults.toml").write_text(_SETTINGS_SCHEMA)
    own = feature("Own", own_apply, requires=own_requires)
    own += "    types: ClassVar = {'unset': (bool,)}\n"
    make_package(
        tmp_path,
        monkeypatch,
        {
            "own": "from typing import ClassVar\n\n" + own,
            "g/need": feature("Need", 'print("need ran")', requires=need_requires),
            "off": feature("Off"),
        },
    )


@pytest.mark.parametrize(
    ("setting", "error"),
    [
        (Setting("own.sub.on", True), None),
        (Setting("own.flag", False), None),
        (Setting("own.flag", True), r"^g\.need: requires features\.own\.flag = true$"),
        (Setting("own.sub.on", False), r"^g\.need: requires features\.own\.sub\.on = false$"),
        (Setting("own.unset", True), r"^g\.need: requires features\.own\.unset = true$"),
        *(
            (
                Setting(key, True),
                rf"^g\.need: requires features\.{re.escape(key)}, which is not a boolean setting$",
            )
            for key in ("own.name", "own.sub", "g.need", "nope.x", "own.nope")
        ),
        (Setting("own.flag", False, "less"), r"^g\.need: requires own\.flag: unknown op less$"),
        (Setting("own.flag", 1), r"^g\.need: requires own\.flag: value must be true or false$"),
        (Setting("off.flag", True), r"^g\.need: requires features\.off\.enabled = true$"),
    ],
)
def test_a_setting_requirement(root, system, tmp_path, monkeypatch, capsys, setting, error):
    _with_a_setting(root, tmp_path, monkeypatch, 'print("own ran")', [], [setting])
    if error is None:
        assert apply("h", root) == 0
        # g.need sorts first by name: only its owner's edge runs own before it.
        assert capsys.readouterr().out == "own ran\nneed ran\nnothing to change\n"
    else:
        with pytest.raises(ConfigError, match=error):
            apply("h", root)


def test_a_setting_requirement_runs_after_its_owner_and_fails_with_it(
    root, system, tmp_path, monkeypatch, capsys
):
    _with_a_setting(root, tmp_path, monkeypatch, 'die("broken")', [], [Setting("own.flag", False)])
    assert apply("h", root) == 1
    assert capsys.readouterr() == ("", "error: own: broken\nerror: g.need: not run, own failed\n")


def test_a_cycle_through_a_setting_s_owner_is_a_config_error(root, system, tmp_path, monkeypatch):
    _with_a_setting(root, tmp_path, monkeypatch, "pass", ["g.need"], [Setting("own.flag", False)])
    msg = r"^g\.need → own → g\.need: each requires the next, so none can run first$"
    with pytest.raises(ConfigError, match=msg):
        apply("h", root)


_EARLY_SCHEMA = """\
[features.early]
enabled = true
[features.late]
enabled = true
flag = true
[features.other]
enabled = true
"""


def _early(body: str) -> str:
    """BODY, a feature's source, with before_packages set."""
    return body + "    before_packages = True\n"


def test_a_feature_before_packages_runs_before_the_install(
    root, system, tmp_path, monkeypatch, capsys
):
    (root / "dotfiles/defaults.toml").write_text(_EARLY_SCHEMA)
    early = feature("Early", 'print(f"early saw {self.system.manager.installs}")', ["tool"])
    late = feature("Late", 'print("late ran")', ["app"])
    make_package(tmp_path, monkeypatch, {"early": _early(early), "late": late})
    asked = []  # installs so far at each depends(): its cache must not predate the install
    depends = FakeManager.depends
    monkeypatch.setattr(
        FakeManager,
        "depends",
        lambda self, names: asked.append(len(self.installs)) or depends(self, names),
    )
    assert apply("h", root) == 0
    assert capsys.readouterr().out == "early saw []\n-> packages: app tool (missing)\nlate ran\n"
    assert system.installs == [["app", "tool"]]
    assert asked and asked[0] == 1


@pytest.mark.parametrize("requirement", ["late", Setting("late.flag", True)])
def test_a_feature_before_packages_cannot_require_a_later_one(
    root, system, tmp_path, monkeypatch, requirement
):
    (root / "dotfiles/defaults.toml").write_text(_EARLY_SCHEMA)
    early = feature("Early", requires=[requirement])
    make_package(tmp_path, monkeypatch, {"early": _early(early), "late": feature("Late")})
    with pytest.raises(ConfigError, match=r"^early: before_packages, so it cannot require late$"):
        apply("h", root)


def test_a_failure_before_packages_blocks_what_runs_after_it_not_the_install(
    root, system, tmp_path, monkeypatch, capsys
):
    (root / "dotfiles/defaults.toml").write_text(_EARLY_SCHEMA)
    make_package(
        tmp_path,
        monkeypatch,
        {
            "early": _early(feature("Early", 'die("broken")')),
            "late": feature("Late", 'print("late ran")', ["app"], requires=["early"]),
            "other": feature("Other", 'print("other ran")', ["x"]),
        },
    )
    assert apply("h", root) == 1
    assert capsys.readouterr() == (
        "-> packages: app x (missing)\nother ran\n",
        "error: early: broken\nerror: late: not run, early failed\n",
    )
    assert system.installs == [["app", "x"]]


def test_a_dry_run_runs_a_feature_before_packages(root, system, tmp_path, monkeypatch, capsys):
    (root / "dotfiles/defaults.toml").write_text(_EARLY_SCHEMA)
    early = feature("Early", 'self.system.report.changed("early change")', ["tool"])
    make_package(tmp_path, monkeypatch, {"early": _early(early)})
    assert apply("h", root, dry_run=True) == 0
    assert capsys.readouterr().out == "-> early change\n-> packages: tool (missing)\n"


def test_packages_that_did_not_install_block_their_features(
    root, system, tmp_path, monkeypatch, capsys
):
    make_package(
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
    assert apply("h", root) == 1
    out, err = capsys.readouterr()
    assert out == "-> packages: postgres (missing)\nok ran\nplain ran\n"
    assert re.fullmatch(
        r"error: packages: unexpected RuntimeError \(mirror down\), "
        r'at tests/test_apply.py:\d+: raise RuntimeError\("mirror down"\)\n'
        r"error: db: not run, packages missing: postgres\n",
        err,
    )


def test_notices_survive_ctrl_c(root, system, tmp_path, monkeypatch, capsys):
    def interrupt(*args):
        raise KeyboardInterrupt

    make_package(
        tmp_path, monkeypatch, {"note": feature("Note", 'self.system.report.notice("reboot")')}
    )
    monkeypatch.setattr(FakeManager, "setup", lambda self: self.report.notice("reboot"))
    monkeypatch.setattr("dotfiles.apply.Apply._features", interrupt)
    with pytest.raises(KeyboardInterrupt):
        apply("h", root)
    assert capsys.readouterr().out.endswith("Notices from this apply:\n    reboot\n")


def test_a_module_holds_the_feature_named_after_it(root, system, tmp_path, monkeypatch):
    make_package(tmp_path, monkeypatch, {"two": feature("A") + feature("B")})
    with pytest.raises(ConfigError, match="^fakeplat.features.two: no feature class Two$"):
        steps({"features": {}}, FakeArch(engine.current()))


def _schema_features(tables: dict, prefix: str = ""):
    """The dotted names of the feature tables of TABLES: those with `enabled`, and packaging."""
    for key, value in tables.items():
        if not isinstance(value, dict):
            continue
        if "enabled" in value or prefix + key == "packaging":
            yield prefix + key
        else:  # a group
            yield from _schema_features(value, f"{prefix}{key}.")


def test_real_features_are_consistent():
    cfg = tomllib.loads(Layout().defaults.read_text())
    schema = set(_schema_features(cfg["features"]))
    for name in schema - {"packaging"}:
        table(cfg["features"], name)["enabled"] = True
    modules = {name for os in (ArchLinuxOs, DebianOs, VoidOs) for name in classes(os)}
    # A module without `enabled` in its table is taken for a group, so it is missing here too.
    assert not modules - schema, f"features not in the schema: {sorted(modules - schema)}"
    assert not schema - modules, f"features without a module: {sorted(schema - modules)}"
    # packages() only reads files
    found = {s.name: s for s in steps(cfg, ArchLinuxOs(engine.current()))}
    assert {n: sorted(s.requires) for n, s in found.items() if s.requires} == {
        "package_tools.paru": ["development.rustup", "packaging"],
        "shell.command_not_found": ["package_tools.pkgfile", "shell.zsh"],
    }


def test_dry_run_on_a_real_host_never_calls_sudo(monkeypatch, capsys):
    monkeypatch.setattr(discovery.platform, "freedesktop_os_release", lambda: {"ID": "arch"})

    def checks_only(argv, check=False, **kwargs):
        if check:  # run(): a mutation
            pytest.fail(f"ran {argv}")
        if argv == ["findmnt", "-no", "FSTYPE", "/"]:  # swap's: a btrfs root
            return subprocess.CompletedProcess(argv, 0, "btrfs\n", "")
        return subprocess.CompletedProcess(argv, 1, "", "")

    monkeypatch.setattr(engine.current().shell, "execute", checks_only)
    cfg = config.resolve("hyper")
    for name in set(_schema_features(cfg["features"])) - {"packaging"}:
        table(cfg["features"], name)["enabled"] = True
    cfg["features"]["packaging"]["pacman"]["flags"] = ["Color"]  # it writes only what is set
    # Every package counts as installed: zsh's among them, and tzdata's zone.
    zsh = engine.current().files.path("/usr/bin/zsh")
    zsh.parent.mkdir(parents=True)
    zsh.touch(mode=0o755)
    zone = engine.current().files.path(
        f"/usr/share/zoneinfo/{cfg['features']['system']['locale']['timezone']}"
    )
    zone.parent.mkdir(parents=True)
    zone.touch()
    assert apply("hyper", dry_run=True, cfg=cfg) == 0
    out = capsys.readouterr().out
    assert "-> /etc/pacman.conf.d/options.conf (missing)\n" in out
    root = engine.current().files.path("/")
    assert sorted(p.relative_to(root).as_posix() for p in root.rglob("*")) == [
        "usr",
        "usr/bin",
        "usr/bin/zsh",
        "usr/share",
        "usr/share/zoneinfo",
        "usr/share/zoneinfo/Europe",
        "usr/share/zoneinfo/Europe/Kyiv",
    ]
