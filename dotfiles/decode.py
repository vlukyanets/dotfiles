"""Decoding of encoded text, for the secret scanner.

A pass finds percent, unicode, hex and base64 encoded runs in the text and
replaces each with its decoded value, keeping a segment per run: where it
was in this text, where its value is in the decoded text, and where it came
from in the original. The scanner runs its rules on each pass, and a match
in decoded text is placed back in the original through its segments.
"""

import base64
import binascii
import re
from collections.abc import Callable
from dataclasses import dataclass

Span = tuple[int, int]

HEX = {c: int(c, 16) for c in "0123456789abcdefABCDEF"}


def printable(data: str) -> bool:
    # From \t (0x09) to ~ (0x7e).
    return all("\x08" < c < "\x7f" for c in data)


def decode_percent(value: str) -> str:
    out = []
    i = 0
    while i < len(value):
        if value[i] == "%" and i + 2 < len(value) and value[i + 1] in HEX and value[i + 2] in HEX:
            c = chr(HEX[value[i + 1]] << 4 | HEX[value[i + 2]])
            if not printable(c):
                return ""
            out.append(c)
            i += 3
            continue
        out.append(value[i])
        i += 1
    return "".join(out)


def decode_hex(value: str) -> str:
    if len(value) % 2 or not any(c.isdigit() for c in value):
        return ""
    out = "".join(chr(HEX[value[i]] << 4 | HEX[value[i + 1]]) for i in range(0, len(value), 2))
    return out if printable(out) else ""


def decode_base64(value: str) -> str:
    if not any(c in "0123456789+/-_" for c in value):
        return ""
    # Go's StdEncoding, then RawURLEncoding (no padding allowed).
    tries: list[tuple[str, bytes | None]] = [(value, None)]
    if not any(c in "+/=" for c in value):
        tries.append((value + "=" * (-len(value) % 4), b"-_"))
    for text, altchars in tries:
        try:
            out = base64.b64decode(text, altchars=altchars, validate=True)
        except (binascii.Error, ValueError):
            continue
        if all(0x08 < b < 0x7F for b in out):
            return out.decode()
    return ""


MULTI_CODE_POINT = re.compile(r"(?:U\+[a-fA-F0-9]{4}(?:\s|$))+", re.ASCII)
ESCAPE = re.compile(r"(?i)\\{1,2}u([a-fA-F0-9]{4})", re.ASCII)
MULTI_ESCAPE = re.compile(r"(?i)(?:\\{1,2}u[a-fA-F0-9]{4})+", re.ASCII)


def rune(code: int) -> str:
    # Go's utf8.EncodeRune writes U+FFFD for a surrogate.
    return "�" if 0xD800 <= code <= 0xDFFF else chr(code)


def decode_unicode(value: str) -> str:
    # A run the encodings pattern finds is all U+XXXX code points or all
    # \uXXXX escapes, so there is no one-at-a-time fallback.
    for pattern, decode in (
        (MULTI_CODE_POINT, lambda s: "".join(rune(int(cp.removeprefix("U+"), 16)) for cp in s.split()
                                             if cp.startswith("U+") and len(cp) >= 6)),
        (MULTI_ESCAPE, lambda s: "".join(rune(int(h, 16)) for h in ESCAPE.findall(s))),
    ):
        matches = pattern.findall(value)
        if matches:
            for match in matches:
                decoded = decode(match) or match
                if decoded != match:
                    value = value.replace(match, decoded, 1)
            return value
    return value


# An earlier one wins when two runs overlap.
ENCODINGS: list[tuple[str, str, Callable[[str], str]]] = [
    ("percent", r"%[0-9A-Fa-f]{2}(?:.*%[0-9A-Fa-f]{2})?", decode_percent),
    ("unicode", r"(?:(?:U\+[a-fA-F0-9]{4}(?:\s|$))+|(?i:(?:\\{1,2}u[a-fA-F0-9]{4})+))", decode_unicode),
    ("hex", r"[0-9A-Fa-f]{32,}", decode_hex),
    ("base64", r"[\w\/+-]{16,}={0,2}", decode_base64),
]
PRECEDENCE = {name: len(ENCODINGS) - i for i, (name, _, _) in enumerate(ENCODINGS)}
DECODERS = {name: decode for name, _, decode in ENCODINGS}
PATTERN = re.compile("|".join(f"(?P<{name}>{p})" for name, p, _ in ENCODINGS), re.ASCII)


def overlaps(a: Span, b: Span) -> bool:
    # Touching counts.
    return b[0] <= a[1] and b[1] >= a[0]


def contains(a: Span, b: Span) -> bool:
    return a[0] <= b[0] and b[1] <= a[1]


@dataclass(eq=False)
class Segment:
    predecessors: list["Segment"]
    original: Span  # In the original text.
    encoded: Span  # In the text this pass decoded.
    decoded: Span  # In the text this pass produced.
    value: str


def to_original(predecessors: list[Segment], decoded: Span) -> Span:
    """Where a span of decoded text came from in the original."""
    if not predecessors:
        return decoded
    encoded = (0, 0)
    for p in predecessors:
        if not overlaps(p.decoded, decoded):
            continue
        if contains(p.decoded, decoded):
            return p.original
        shifted = (p.encoded[0] + min(p.decoded[0], decoded[0]) - p.decoded[0],
                   p.encoded[1] + max(p.decoded[1], decoded[1]) - p.decoded[1])
        encoded = shifted if encoded[1] == 0 else (min(encoded[0], shifted[0]), max(encoded[1], shifted[1]))
    if encoded[1] == 0:
        return decoded
    return to_original(predecessors[0].predecessors, encoded)


def encoded_runs(data: str) -> list[tuple[str, Span]]:
    runs = [
        (next(name for name in DECODERS if m[name] is not None), m.span())
        for m in PATTERN.finditer(data)
    ]
    if len(runs) == 1:
        return runs
    kept = []
    for i, (name, span) in enumerate(runs):
        neighbours = runs[i - 1:i] + runs[i + 1:i + 2]
        if any(overlaps(span, s) and PRECEDENCE[n] > PRECEDENCE[name] for n, s in neighbours):
            continue
        kept.append((name, span))
    return kept


class Decoder:
    def __init__(self) -> None:
        self.cache: dict[str, str] = {}

    def decode(self, data: str, predecessors: list[Segment]) -> tuple[str, list[Segment]]:
        """One pass: data with its encoded runs decoded, and their segments."""
        segments = []
        shift = 0
        for name, (start, end) in encoded_runs(data) if data else []:
            encoded = data[start:end]
            if encoded not in self.cache:
                self.cache[encoded] = DECODERS[name](encoded)
            value = self.cache[encoded]
            if not value:
                continue
            segments.append(Segment(
                predecessors=predecessors,
                original=to_original(predecessors, (start, end)),
                encoded=(start, end),
                decoded=(start + shift, start + shift + len(value)),
                value=value,
            ))
            shift += len(value) - len(encoded)
        if not segments:
            return data, []
        out, pos = [], 0
        for s in segments:
            out += [data[pos:s.encoded[0]], s.value]
            pos = s.encoded[1]
        out.append(data[pos:])
        return "".join(out), segments


def current_line(segments: list[Segment], text: str) -> str:
    """The decoded text's line around the segments."""
    start = min(s.decoded[0] for s in segments)
    end = max(s.decoded[1] for s in segments)
    left = text.rfind("\n", 0, start + 1)
    right = text.find("\n", end)
    return text[max(left, 0):right if right >= 0 else len(text)]
