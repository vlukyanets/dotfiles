from pathlib import Path

import pytest

from dotfiles.config import ConfigError
from dotfiles.render import check, render


def write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    write(tmp_path, "defaults.toml", '[git]\nname = ""\n[features.zsh]\nenabled = false\n')
    write(tmp_path, "hosts/on.toml", '[git]\nname = "Ann"\n[features.zsh]\nenabled = true\n')
    return tmp_path


def tree(out: Path) -> dict[str, tuple[str, str]]:
    """path -> (mode, content) for every path under OUT."""
    return {
        p.relative_to(out).as_posix(): (
            oct(p.stat().st_mode & 0o777)[2:],
            p.read_text() if p.is_file() else "",
        )
        for p in sorted(out.rglob("*"))
    }


def test_plain_files_templates_and_modes(root, tmp_path):
    write(root, "home/.plain", "as is {{ x }}\n")
    write(root, "home/.gitconfig.j2", "name = {{ git.name }} on {{ host }}\n")
    write(root, "home/.ssh/config", "Host *\n")
    write(root, "home/bin/run.sh", "#!/bin/sh\n")
    write(
        root,
        "home.toml",
        '[".ssh"]\nmode = "700"\n[".ssh/config"]\nmode = "600"\n["bin/run.sh"]\nmode = "755"\n',
    )
    out = tmp_path / "out"
    assert render("on", out, root) == [
        ".gitconfig",
        ".plain",
        ".ssh",
        ".ssh/config",
        "bin",
        "bin/run.sh",
    ]
    assert tree(out) == {
        ".gitconfig": ("644", "name = Ann on on\n"),
        ".plain": ("644", "as is {{ x }}\n"),
        ".ssh": ("700", ""),
        ".ssh/config": ("600", "Host *\n"),
        "bin": ("755", ""),
        "bin/run.sh": ("755", "#!/bin/sh\n"),
    }


def test_gates_on_files_and_directories(root, tmp_path):
    write(root, "home/.zshrc.j2", "zsh\n")
    write(root, "home/.config/zsh/extra", "x\n")
    write(root, "home/.always", "y\n")
    write(
        root,
        "home.toml",
        '[".zshrc"]\nwhen = "features.zsh.enabled"\n'
        '[".config/zsh"]\nwhen = "features.zsh.enabled and git.name == \'Ann\'"\n',
    )
    assert render("on", tmp_path / "on", root) == [
        ".always",
        ".config",
        ".config/zsh",
        ".config/zsh/extra",
        ".zshrc",
    ]
    assert render("off", tmp_path / "off", root) == [".always", ".config"]


def test_whitespace_control(root, tmp_path):
    write(root, "home/f.j2", "a\n{% if features.zsh.enabled %}\n  b\n{% endif %}\nc\n")
    render("on", tmp_path / "out", root)
    assert (tmp_path / "out/f").read_text() == "a\n  b\nc\n"


def test_current_file_is_passed_to_templates(root, tmp_path):
    write(root, "home/.config/app.j2", "was: {{ current }}")
    write(tmp_path, "home/.config/app", "old")
    render("on", tmp_path / "with", root, current=tmp_path / "home")
    render("on", tmp_path / "without", root)
    assert (tmp_path / "with/.config/app").read_text() == "was: old"
    assert (tmp_path / "without/.config/app").read_text() == "was: "


@pytest.mark.parametrize(
    ("files", "error"),
    [
        ({"home/f.j2": "x\n{{ nope }}\n"}, "home/f.j2:2: on: 'nope' is undefined"),
        ({"home/f.j2": "{{ git.nope }}"}, "home/f.j2:1: on: 'dict object' has no attribute 'nope'"),
        (
            {"home/f.j2": "{% if %}"},
            "home/f.j2:1: on: Expected an expression, got 'end of statement block'",
        ),
        ({"home/f.j2": '{{ fail("bad key") }}'}, "home/f.j2:1: on: bad key"),
        (
            {"home/f": "", "home.toml": '["g"]\nmode = "600"\n'},
            "home.toml: g: no such file or directory under home/",
        ),
        (
            {"home/f": "", "home.toml": '["f"]\nmode = 600\n'},
            'home.toml: f: mode must be three octal digits, like "600"',
        ),
        (
            {"home/f": "", "home.toml": '["f"]\nowner = "x"\n'},
            "home.toml: f: only mode and when are allowed",
        ),
        (
            {"home/f": "", "home.toml": '["f"]\nwhen = "nope"\n'},
            "home.toml: f: when: on: 'nope' is undefined",
        ),
    ],
)
def test_errors_name_the_file_and_host(root, tmp_path, files, error):
    for rel, text in files.items():
        write(root, rel, text)
    with pytest.raises(ConfigError) as e:
        render("on", tmp_path / "out", root)
    assert str(e.value) == error


def test_out_must_be_empty(root, tmp_path):
    write(tmp_path, "out/stale", "")
    with pytest.raises(ConfigError, match="not empty"):
        render("on", tmp_path / "out", root)


def test_check_renders_every_host(root):
    write(root, "home/f.j2", "{{ git.name or fail('no name') }}")
    assert check(root) == {"on": None, "unknown-host": "home/f.j2:1: unknown-host: no name"}


def test_registries_reach_templates_and_names_are_checked(root, tmp_path):
    write(
        root,
        "defaults.toml",
        '[git]\nname = ""\n[features.zsh]\nenabled = false\n'
        '[features.locale]\nlanguages = ["en"]\n',
    )
    write(root, "hosts/bad.toml", '[features.locale]\nlanguages = ["en", "xx"]\n')
    write(root, "data/languages.toml", '[languages.en]\nxkb = "us"\n')
    write(
        root,
        "home/kb.j2",
        '{{ features.locale.languages | map("extract", languages) | map(attribute="xkb") | join(",") }}\n',
    )
    render("on", tmp_path / "out", root)
    assert (tmp_path / "out/kb").read_text() == "us\n"
    with pytest.raises(ConfigError) as e:
        render("bad", tmp_path / "bad", root)
    assert str(e.value) == "bad: features.locale.languages: 'xx' is not in data/ (languages)"


def test_quote_and_inline_if(root, tmp_path):
    write(root, "home/f.j2", '{{ git.name | quote }} {{ "on" if features.zsh.enabled else "" }}|\n')
    render("on", tmp_path / "out", root)
    assert (tmp_path / "out/f").read_text() == '"Ann" on|\n'
