"""Tests for the secret scanner and the rules in secret_leaks.toml."""

import base64
import re
import subprocess
from pathlib import Path

import pytest

from dotfiles import cli, secrets

CONFIG = secrets.load(Path(__file__).parents[1] / "secret_leaks.toml")

# Built from pieces, so that secret scanners do not flag this file.
GITHUB_SAMPLE = "gh" + "o_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
SECRETS = [
    (GITHUB_SAMPLE, "github-oauth"),
    ("-----BEGIN OPENSSH " + "PRIVATE KEY-----", "dotfiles-private-key"),
    ("AKIA" + "Z7QW3RTY5UIOPLKJ", "aws-access-token"),
    ("AKIA" + "IOSFODNN7EXAMPLE", "dotfiles-aws-access-key"),
    ("xox" + "b-1234567890-abcdefghij", "dotfiles-slack-token"),
    ("sk-" + "ant-" + "a" * 40, "dotfiles-api-key"),
    ("psk=correct-horse-battery", "dotfiles-password-or-key"),
    ("  Passphrase = correct horse battery", "dotfiles-password-or-key"),
    ("wifi_password: hunter22", "dotfiles-password-or-key"),
]
ORDINARY = [
    "PasswordAuthentication no",
    "# token: <put your token here>",
    "password=",
    "password: true",
    "Include /etc/ssh/sshd_config.d/*.conf",
    # Placeholders, dropped by the global allowlist.
    "password = ${WIFI_PASSWORD}",
    "psk={{ .psk }}",
]


def find(text, path="etc/conf"):
    return secrets.find(CONFIG, text, path)


# Test ids name the rule, so the secrets stay out of pytest's output and cache.
@pytest.mark.parametrize("line, rule", SECRETS, ids=[f"{i}-{rule}" for i, (_, rule) in enumerate(SECRETS)])
def test_finds_each_kind_of_secret(line, rule):
    assert find(f"# a config\n{line}\n") == [(2, rule)]


@pytest.mark.parametrize("line", ORDINARY)
def test_does_not_flag_ordinary_lines(line):
    assert find(line) == []


def test_reports_a_line_once_and_a_specific_rule_over_a_generic_one():
    # Matches generic-api-key, github-oauth and the password rule; the
    # generic finding gives way to github-oauth's.
    assert find(f"token = {GITHUB_SAMPLE}") == [(1, "github-oauth")]


def test_skips_a_line_marked_allowed():
    assert find("psk=correct-horse-battery  # secret-leaks:allow") == []


def test_skips_a_file_in_the_global_allowlist():
    assert find("psk=correct-horse-battery", path="web/yarn.lock") == []


def test_finds_a_secret_across_lines():
    key = "-----BEGIN RSA " + "PRIVATE KEY-----\n" + "MIIEow" * 20 + "\n-----END RSA " + "PRIVATE KEY-----"
    assert (2, "private-key") in find(f"x\n{key}\n")


def b64(text):
    return base64.b64encode(text.encode()).decode()


ENCODED = [
    ("base64", f"data={b64(f'token: {GITHUB_SAMPLE}')}"),
    ("base64 twice", f"data={b64('x=' + b64(f'token: {GITHUB_SAMPLE}'))}"),
    ("hex", f"v={f'token: {GITHUB_SAMPLE}'.encode().hex()}"),
    ("percent", "u=" + "".join(f"%{ord(c):02X}" for c in GITHUB_SAMPLE)),
    ("unicode escapes", 's="' + "".join(f"\\u{ord(c):04x}" for c in GITHUB_SAMPLE) + '"'),
    ("code points", "s=" + " ".join(f"U+{ord(c):04X}" for c in GITHUB_SAMPLE)),
]


@pytest.mark.parametrize("text", [t for _, t in ENCODED], ids=[name for name, _ in ENCODED])
def test_finds_an_encoded_secret_on_its_line(text):
    assert find(f"a\nb\n{text}\n") == [(3, "github-oauth")]


def test_decodes_at_most_five_passes():
    text = f"token: {GITHUB_SAMPLE}"
    for _ in range(5):
        text = "x=" + b64(text)
    assert find(text) == [(1, "github-oauth")]
    assert find("x=" + b64(text)) == []


def test_every_regex_compiles_in_python():
    assert len(CONFIG.rules) == 228
    assert [r.id for r in CONFIG.rules[-6:]] == [
        "dotfiles-github-token", "dotfiles-private-key", "dotfiles-aws-access-key",
        "dotfiles-slack-token", "dotfiles-api-key", "dotfiles-password-or-key",
    ]


def test_entropy_is_shannon_entropy_by_bytes():
    assert secrets.entropy("") == 0
    assert secrets.entropy("aaaa") == 0
    assert secrets.entropy("1223334444") == pytest.approx(1.846439, abs=1e-6)
    # Divided by the length in bytes, as Go's len() does.
    assert secrets.entropy("é") == pytest.approx(0.5)


def config(tmp_path, toml):
    (tmp_path / "rules.toml").write_text(toml)
    return secrets.load(tmp_path / "rules.toml")


def test_keywords_gate_a_rule(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "r"
regex = '''key-\\d+'''
keywords = ["Vault"]
""")
    assert secrets.find(c, "key-123", "f") == []
    assert secrets.find(c, "vault key-123", "f") == [(1, "r")]


def test_secret_group_and_entropy_pick_and_drop(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "r"
regex = '''(id)=(\\w+)'''
secretGroup = 2
entropy = 2.5
""")
    assert secrets.find(c, "id=aaaaaaaaaaaa", "f") == []
    assert secrets.find(c, "id=x9Kq2LmZ7vP4", "f") == [(1, "r")]


def test_first_non_empty_group_is_the_secret(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "r"
regex = '''(a)?=(\\w+)'''
[[rules.allowlists]]
regexes = ['''^ok$''']
""")
    assert secrets.find(c, "=ok", "f") == []
    assert secrets.find(c, "=no", "f") == [(1, "r")]


def test_rule_allowlists_by_stopword_target_and_condition(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "r"
regex = '''s=(\\w+)'''
[[rules.allowlists]]
stopwords = ["example"]
[[rules.allowlists]]
regexTarget = "line"
regexes = ['''^#''']
[[rules.allowlists]]
condition = "AND"
paths = ['''^test/''']
regexes = ['''^fake''']
""")
    assert secrets.find(c, "s=myEXAMPLEkey", "f") == []
    assert secrets.find(c, "# s=real", "f") == []
    assert secrets.find(c, "s=fake1", "test/a") == []
    assert secrets.find(c, "s=fake1", "src/a") == [(1, "r")]
    assert secrets.find(c, "s=real1", "test/a") == [(1, "r")]


def test_rule_allowlist_path_skips_the_file(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "r"
regex = '''s=\\w+'''
[[rules.allowlists]]
paths = ['''\\.md$''']
""")
    assert secrets.find(c, "s=x", "README.md") == []
    assert secrets.find(c, "s=x", "conf") == [(1, "r")]


def test_a_path_rule_flags_the_file_itself(tmp_path):
    c = config(tmp_path, """
[[rules]]
id = "p12"
path = '''\\.p12$'''
""")
    assert secrets.find(c, "", "keys/me.p12") == [(0, "p12")]
    assert secrets.report("keys/me.p12", [(0, "p12")]) == ["keys/me.p12: p12"]


DIFF = """\
diff --git a/etc/new b/etc/new
new file mode 100644
--- /dev/null
+++ b/etc/new
@@ -0,0 +1,2 @@
+first
+++ psk=looks-like-a-header
diff --git a/etc/old b/etc/old
--- a/etc/old
+++ b/etc/old
@@ -3 +3 @@
-before
+after
@@ -10,0 +11,2 @@
+eleven
+twelve
diff --git a/gone b/gone
deleted file mode 100644
--- a/gone
+++ /dev/null
@@ -1 +0,0 @@
-was here
diff --git "a/odd\\tname" "b/odd\\tname"
--- "a/odd\\tname"
+++ "b/odd\\tname"
@@ -1 +1 @@
+quoted
"""


def test_added_hunks_follows_paths_and_line_numbers():
    assert list(secrets.added_hunks(DIFF)) == [
        ("etc/new", 1, "first\n++ psk=looks-like-a-header"),
        ("etc/old", 3, "after"),
        ("etc/old", 11, "eleven\ntwelve"),
        ('"b/odd\\tname"', 1, "quoted"),
    ]


def git(repo, *args):
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def test_scan_staged_finds_only_staged_added_lines(tmp_path):
    git(tmp_path, "init", "-q")
    (tmp_path / "old").write_text("psk=committed-before\n")
    git(tmp_path, "add", "old")
    git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "old")
    (tmp_path / "old").write_text("psk=committed-before\nok\npsk=staged-now\n")
    (tmp_path / "unstaged").write_text("psk=not-staged\n")
    git(tmp_path, "add", "old")

    assert secrets.scan_staged(CONFIG, tmp_path) == ["old:3: dotfiles-password-or-key"]


def test_scan_history_finds_a_secret_a_later_commit_removed(tmp_path):
    git(tmp_path, "init", "-q")
    commit = ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "c"]
    (tmp_path / "conf").write_text("ok\npsk=correct-horse-battery\n")
    git(tmp_path, "add", "conf")
    git(tmp_path, *commit)
    first = subprocess.run(["git", "-C", str(tmp_path), "rev-parse", "HEAD"],
                           capture_output=True, text=True).stdout[:12]
    (tmp_path / "conf").write_text("ok\n")
    git(tmp_path, "add", "conf")
    git(tmp_path, *commit)

    assert secrets.scan_paths(CONFIG, [tmp_path / "conf"]) == []
    assert secrets.scan_history(CONFIG, tmp_path) == [f"{first}:conf:2: dotfiles-password-or-key"]


def test_scan_paths_walks_a_directory_but_not_tool_directories(tmp_path):
    (tmp_path / "etc").mkdir()
    (tmp_path / "etc/conf").write_text("ok\npsk=correct-horse-battery\n")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv/lib.py").write_text("password = 'in a dependency'\n")

    assert secrets.scan_paths(CONFIG, [tmp_path]) == [
        f"{tmp_path}/etc/conf:2: dotfiles-password-or-key"
    ]


def test_command_exits_1_and_never_prints_the_value(tmp_path, capsys):
    (tmp_path / "hosts.yml").write_text(f"oauth_token: {GITHUB_SAMPLE}\n")
    (tmp_path / "clean").write_text("ok\n")

    assert cli.main(["scan", str(tmp_path / "clean")]) == 0
    assert cli.main(["scan", str(tmp_path / "hosts.yml")]) == 1
    err = capsys.readouterr().err
    assert re.search(rf"{tmp_path}/hosts\.yml:1: \S+", err)
    assert GITHUB_SAMPLE not in err


def test_command_reports_a_missing_path(capsys):
    assert cli.main(["scan", "/no/such/path"]) == 2
    assert "no such file" in capsys.readouterr().err
