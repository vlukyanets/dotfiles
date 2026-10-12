"""dotfiles scan: finds what looks like a secret, by the rules in secret_leaks.toml.

How a rule applies: it runs only if one of its keywords is in the text; a
path rule matches the file name; the secret is the first non-empty capture
group, or the secretGroup one; a secret at or below the rule's entropy is
dropped; and the global and rule allowlists drop files by path and
findings by regex or stopword. A line marked `secret-leaks:allow` is
skipped. Findings name the file, the line and the rule id, never the value.

Encoded secrets are found too: dotfiles/decode.py decodes percent,
unicode, hex and base64 runs, up to five passes deep.
"""

import bisect
import math
import re
import subprocess
import tomllib
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from dotfiles import decode

ALLOW = "secret-leaks:allow"
MAX_DECODE_DEPTH = 5
# Directories a scan of a directory does not enter.
SKIP = {".git", ".venv", "__pycache__", ".pytest_cache"}


def compile_regex(pattern: str) -> re.Pattern[str]:
    # ASCII, so \w, \d, \s and \b mean what they mean in Go's RE2.
    return re.compile(pattern, re.ASCII)


@dataclass
class Allowlist:
    all_of: bool  # condition = "AND"
    target: str  # what the regexes check: "secret", "match" or "line"
    regexes: list[re.Pattern[str]]
    paths: list[re.Pattern[str]]
    stopwords: list[str]
    commits: list[str]

    @classmethod
    def load(cls, table: dict) -> "Allowlist":
        return cls(
            all_of=table.get("condition", "OR").upper() == "AND",
            target=table.get("regexTarget", "secret"),
            regexes=[compile_regex(r) for r in table.get("regexes", [])],
            paths=[compile_regex(r) for r in table.get("paths", [])],
            stopwords=[w.lower() for w in table.get("stopwords", [])],
            commits=table.get("commits", []),
        )

    def path_allowed(self, path: str) -> bool:
        return any(p.search(path) for p in self.paths)

    def skips_file(self, path: str) -> bool:
        """Whether the allowlist drops a whole file. There is never a commit here."""
        if not self.all_of:
            return self.path_allowed(path)
        if self.regexes or self.stopwords:
            return False  # Decided per finding.
        checks = ([False] if self.commits else []) + ([self.path_allowed(path)] if self.paths else [])
        return all(checks)

    def skips_finding(self, secret: str, match: str, line: str, path: str) -> bool:
        """Whether the allowlist drops a finding."""
        target = {"match": match, "line": line}.get(self.target, secret)
        regex = bool(target) and any(r.search(target) for r in self.regexes)
        stopword = bool(secret) and any(w in secret.lower() for w in self.stopwords)
        if not self.all_of:
            return regex or stopword
        checks = (
            ([False] if self.commits else [])
            + ([self.path_allowed(path)] if self.paths else [])
            + ([regex] if self.regexes else [])
            + ([stopword] if self.stopwords else [])
        )
        return all(checks)


@dataclass
class Rule:
    id: str
    regex: re.Pattern[str] | None
    path: re.Pattern[str] | None
    secret_group: int
    entropy: float
    keywords: list[str]
    allowlists: list[Allowlist]

    @classmethod
    def load(cls, table: dict) -> "Rule":
        return cls(
            id=table["id"],
            regex=compile_regex(table["regex"]) if "regex" in table else None,
            path=compile_regex(table["path"]) if "path" in table else None,
            secret_group=table.get("secretGroup", 0),
            entropy=table.get("entropy", 0.0),
            keywords=[k.lower() for k in table.get("keywords", [])],
            allowlists=[Allowlist.load(a) for a in table.get("allowlists", [])],
        )


@dataclass
class Config:
    rules: list[Rule]
    allowlists: list[Allowlist]


def load(path: Path) -> Config:
    """A rules file: its rules, and its global allowlists."""
    table = tomllib.loads(path.read_text())
    allowlists = [table["allowlist"]] if "allowlist" in table else []
    return Config(
        rules=[Rule.load(r) for r in table["rules"]],
        allowlists=[Allowlist.load(a) for a in allowlists + table.get("allowlists", [])],
    )


def entropy(text: str) -> float:
    """Shannon entropy over characters, divided by the length in bytes."""
    if not text:
        return 0.0
    size = len(text.encode())
    return -sum(n / size * math.log2(n / size) for n in Counter(text).values())


def find(config: Config, text: str, path: str, first_line: int = 1) -> list[tuple[int, str]]:
    """The line and the rule id of each finding in text, one per line, the
    first rule winning; line 0 is a finding by the file's name. first_line is
    the number of text's first line in the file.

    The rules run on the text and then on up to
    MAX_DECODE_DEPTH passes of decoding it, a decoded match counting only if
    it touches what the last pass decoded."""
    found: dict[int, str] = {}
    for line, rule_id, _ in find_values(config, text, path):
        found.setdefault(line + first_line - 1 if line else 0, rule_id)
    return sorted(found.items())


def find_values(config: Config, text: str, path: str) -> list[tuple[int, str, str]]:
    """The line, the rule id and the secret of every finding in text, as find
    sees them before it keeps one per line; the secret of a decoded finding
    is the decoded one."""
    if any(a.skips_file(path) for a in config.allowlists):
        return []
    newlines = [m.start() for m in re.finditer("\n", text)]
    findings: list[tuple[int, str, str]] = []  # line, rule id, secret
    current, segments = text, []
    decoder = decode.Decoder()
    for depth in range(MAX_DECODE_DEPTH + 1):
        lower = current.lower()
        for rule in config.rules:
            if rule.keywords and not any(k in lower for k in rule.keywords):
                continue
            findings += detect(config, rule, text, newlines, current, segments, path)
        if depth == MAX_DECODE_DEPTH:
            break
        current, segments = decoder.decode(current, segments)
        if not segments:
            break
    return drop_generic_duplicates(findings)


def detect(
    config: Config, rule: Rule, text: str, newlines: list[int],
    current: str, segments: list[decode.Segment], path: str,
) -> list[tuple[int, str, str]]:
    """The (line, rule id, secret) of each finding of
    one rule in current, the text after some passes of decoding, with lines
    counted in text, the original."""
    if any(a.skips_file(path) for a in rule.allowlists):
        return []
    if rule.path:
        if not rule.path.search(path):
            return []
        if rule.regex is None:
            return [(0, rule.id, "")]
    if rule.regex is None:
        return []
    findings = []
    for m in rule.regex.finditer(current):
        match = m[0].strip("\n")
        if segments:
            touched = [s for s in segments if decode.overlaps(s.decoded, m.span())]
            if not touched:
                continue  # Found already, before this pass.
            start, end = decode.to_original(touched, m.span())
        else:
            start, end = m.start(), m.start() + len(match)
        # A line starts at the newline before it, so a match that starts
        # with a newline is on the next line.
        first = bisect.bisect_left(newlines, start + 1)
        last = bisect.bisect_left(newlines, end)
        line_start = newlines[first - 1] + 1 if first else 0
        line_end = max(newlines[last] if last < len(newlines) else len(text), end)
        line = text[line_start:line_end]
        if ALLOW in line:
            continue
        current_line = decode.current_line(touched, current) if segments else line
        # The secret: the secretGroup group, or the first non-empty one.
        value = match
        groups = rule.regex.search(match)
        if groups and rule.regex.groups:
            if rule.secret_group:
                value = groups[rule.secret_group] or ""
            else:
                value = next((g for g in groups.groups() if g), value)
        if rule.entropy and entropy(value) <= rule.entropy:
            continue
        if any(a.skips_finding(value, match, current_line, path) for a in config.allowlists + rule.allowlists):
            continue
        findings.append((first + 1, rule.id, value))
    return findings


def drop_generic_duplicates(findings: list[tuple[int, str, str]]) -> list[tuple[int, str, str]]:
    """A generic rule's finding goes when another rule found
    a secret holding it on the same line."""
    return [
        (line, rule_id, value) for line, rule_id, value in findings
        if "generic" not in rule_id.lower() or not any(
            line == l2 and rule_id != r2 and value in v2 and "generic" not in r2.lower()
            for l2, r2, v2 in findings
        )
    ]


def find_secrets(config: Config, data: bytes, path: str) -> list[tuple[int, str]]:
    """find over a whole file's contents."""
    return find(config, data.decode(errors="replace"), path)


def added_hunks(diff: str) -> Iterator[tuple[str, int, str]]:
    """The (path, first line number, text) of the lines each hunk of a
    `git diff -U0` adds."""
    path = ""
    header = False  # Between `diff --git` and the first hunk, where +++ is the path.
    start, lines = 0, []
    for line in diff.splitlines():
        if line.startswith("diff --git ") or line.startswith("@@ "):
            if lines:
                yield path, start, "\n".join(lines)
            lines = []
        if line.startswith("diff --git "):
            header = True
        elif header and line.startswith("+++ "):
            # A path git quotes ("b/…") is kept as git shows it: it is only
            # printed, and its lines must not be skipped. A deleted file's
            # /dev/null adds no lines.
            path = line[4:].removeprefix("b/")
        elif line.startswith("@@ "):
            header = False
            # @@ -old[,count] +new[,count] @@
            start = int(re.match(r"@@ -\S+ \+(\d+)", line)[1])
        elif not header and line.startswith("+"):
            lines.append(line[1:])
    if lines:
        yield path, start, "\n".join(lines)


def report(path: str, findings: list[tuple[int, str]]) -> list[str]:
    return [f"{path}:{n}: {d}" if n else f"{path}: {d}" for n, d in findings]


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotePath=false", *args,
         "-U0", "--no-color", "--no-ext-diff"],
        check=True, capture_output=True, text=True, errors="replace",
    ).stdout


def scan_diff(config: Config, diff: str, prefix: str = "") -> list[str]:
    findings = []
    for path, first_line, text in added_hunks(diff):
        findings += report(prefix + path, find(config, text, path, first_line))
    return findings


def scan_staged(config: Config, repo: Path) -> list[str]:
    """Findings in the lines the staged changes add, hunk by hunk."""
    return scan_diff(config, git(repo, "diff", "--cached"))


def scan_history(config: Config, repo: Path) -> list[str]:
    """Findings in the lines each commit reachable from HEAD adds, named
    <commit>:<path>:<line>, so a secret removed later is found too."""
    findings = []
    for chunk in git(repo, "log", "-p", "--format=%x00%H").split("\0")[1:]:
        commit, _, diff = chunk.partition("\n")
        findings += scan_diff(config, diff, f"{commit[:12]}:")
    return findings


def scan_paths(config: Config, paths: Iterable[Path]) -> list[str]:
    """Findings in whole files; a directory is scanned file by file."""
    findings = []
    for path in paths:
        if path.is_dir():
            files = sorted(
                p for p in path.rglob("*")
                if p.is_file() and not SKIP & set(p.relative_to(path).parts)
            )
        else:
            files = [path]
        for file in files:
            findings += report(str(file), find_secrets(config, file.read_bytes(), str(file)))
    return findings
