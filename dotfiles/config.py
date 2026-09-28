"""Host configuration: the defaults, then the host's chain of profiles and hosts."""

import copy
import os
import re
import tomllib
from pathlib import Path

import tomli_w

ROOT = Path(__file__).resolve().parent.parent
# The schema: every key, its type and its default.
DEFAULTS = "dotfiles/defaults.toml"

# TOML's names, so an error reads like the file the user is editing.
KINDS = {
    bool: "boolean",
    int: "integer",
    float: "float",
    str: "string",
    list: "array",
    dict: "table",
}
SECRETS_BACKENDS = ("none", "rbw")
# Keys that take either of two types; the default's type is the first.
EITHER = {"features.packaging.makepkg.jobs": (int, str)}
# The options pacman.conf takes without a value.
PACMAN_FLAGS = (
    "CheckSpace",
    "Color",
    "DisableDownloadTimeout",
    "DisableSandbox",
    "ILoveCandy",
    "NoProgressBar",
    "UseSyslog",
    "VerbosePkgLists",
)
# What a type cannot say, checked on the merged config: key -> (test, what it must be).
RULES = {
    "secrets.backend": (lambda v: v in SECRETS_BACKENDS, f"one of {', '.join(SECRETS_BACKENDS)}"),
    "features.packaging.pacman.parallel_downloads": (lambda v: v >= 0, "0 or more"),
    "features.packaging.pacman.flags": (
        lambda v: set(v) <= set(PACMAN_FLAGS),
        f"names from {', '.join(PACMAN_FLAGS)}",
    ),
    "features.packaging.makepkg.jobs": (
        lambda v: v >= 0 if type(v) is int else re.fullmatch(r"[1-9][0-9]*%", v),
        'a number of threads, or a percent of the cores like "50%"',
    ),
    "features.packaging.makepkg.packager": (
        lambda v: v == "" or re.fullmatch(r"[^<>]+ <[^<>]+>", v),
        '"Name <email>"',
    ),
}


class ConfigError(Exception):
    """A config, template or checkout that is wrong; the message names where."""


class MissingKey(KeyError):
    """A key the resolved config does not have: a bug in the code reading it."""

    def __str__(self) -> str:
        """The message alone, without KeyError's quotes."""
        return self.args[0]


class Settings(dict):
    """A table of the resolved config: a missing key fails naming its dotted path."""

    def __init__(self, data: dict | None = None, dotted: str = ""):
        """DATA with every table made a Settings that knows its DOTTED path."""
        super().__init__(
            (k, Settings(v, f"{dotted}{k}.") if isinstance(v, dict) else v)
            for k, v in (data or {}).items()
        )
        self._dotted = dotted

    def __missing__(self, key):
        """Fail naming the full dotted key, not just KEY."""
        raise MissingKey(f"{self._dotted}{key}: no such key in {DEFAULTS}")

    def plain(self) -> dict:
        """A copy made of plain dicts, for code that should not see Settings."""
        return {k: v.plain() if isinstance(v, Settings) else v for k, v in self.items()}


def load(path: Path, root: Path) -> dict:
    """PATH parsed as TOML; a syntax error names the file."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        where = path.relative_to(root) if path.is_relative_to(root) else shown(path)
        raise ConfigError(f"{where}: {e}") from None


def local_path() -> Path:
    """This machine's config, written by `dotfiles init`."""
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "dotfiles/config.toml"


def shown(path: Path) -> str:
    """PATH with ~ for the home directory, the way errors and changes name it."""
    return f"~/{path.relative_to(Path.home())}" if path.is_relative_to(Path.home()) else str(path)


def kind(value) -> str:
    """VALUE's TOML type, as errors name it."""
    return KINDS.get(type(value), type(value).__name__)


def validate(data: dict, schema: dict, where: str, prefix: str = "") -> None:
    """Every key of DATA exists in SCHEMA at the same path, with the same type."""
    for key, value in data.items():
        dotted = prefix + key
        if key not in schema:
            raise ConfigError(f"{where}: {dotted}: unknown key")
        want = schema[key]
        types = EITHER.get(dotted, (type(want),))
        # type() rather than isinstance(): a bool is an int to isinstance.
        if type(value) not in types:
            must = " or ".join(KINDS[t] for t in types)
            raise ConfigError(f"{where}: {dotted}: must be {must}, got {kind(value)}")
        if isinstance(want, dict):
            validate(value, want, where, dotted + ".")


def merge(into: dict, data: dict) -> None:
    """Tables merge recursively; scalars and arrays are replaced, never appended."""
    for key, value in data.items():
        if isinstance(value, dict):
            merge(into[key], value)
        else:
            into[key] = value


def names(root: Path) -> dict[str, Path]:
    """Every profile and host by name. One namespace, so `extends` needs no prefix."""
    found: dict[str, Path] = {}
    paths = sorted((root / "profiles").glob("*.toml")) + sorted((root / "hosts").glob("*.toml"))
    for path in paths:
        if path.stem in found:
            other = found[path.stem].relative_to(root)
            raise ConfigError(f"{path.relative_to(root)}: {path.stem!r} is also {other}")
        found[path.stem] = path
    return found


def chain(host: str, root: Path) -> list[tuple[str, dict]]:
    """HOST's files, each (path, data), parents before children; [] for an unknown host."""
    known = names(root)
    order: list[tuple[str, dict]] = []
    done: set[str] = set()

    def visit(name: str, stack: list[str]) -> None:
        """NAME's parents, then NAME itself, each once; fail on a cycle."""
        if name in stack:
            raise ConfigError(f"extends: cycle {' → '.join(stack[stack.index(name) :] + [name])}")
        if name in done:
            return
        where = str(known[name].relative_to(root))
        data = load(known[name], root)
        parents = data.pop("extends", [])
        if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
            raise ConfigError(f"{where}: extends: must be an array of strings")
        for parent in parents:
            if parent not in known:
                raise ConfigError(f"{where}: extends: no profile or host {parent!r}")
            visit(parent, stack + [name])
        done.add(name)
        order.append((where, data))

    if host in known and known[host].parent.name == "hosts":
        visit(host, [])
    return order


def leaves(data: dict, prefix: str = ""):
    """(dotted key, value) for every non-table value; arrays are leaves."""
    for key, value in data.items():
        if isinstance(value, dict):
            yield from leaves(value, prefix + key + ".")
        else:
            yield prefix + key, value


def resolve_with_sources(
    host: str, root: Path = ROOT, local: Path | None = None
) -> tuple[dict, dict[str, str]]:
    """HOST's merged, validated config and the file each key comes from."""
    schema = load(root / DEFAULTS, root)
    config = copy.deepcopy(schema)
    sources = {key: DEFAULTS for key, _ in leaves(schema)}
    if local is None:
        files = chain(host, root)
    elif local.is_file():
        files = [(shown(local), load(local, root))]
    else:
        raise ConfigError(
            f"no {shown(local)} — run dotfiles init <host>, or pass --source <checkout>"
        )
    for where, data in files:
        validate(data, schema, where)
        merge(config, data)
        sources.update((key, where) for key, _ in leaves(data))
    values = dict(leaves(config))
    for key, (test, what) in RULES.items():
        if key in values and not test(values[key]):
            raise ConfigError(f"{host}: {key}: must be {what}, got {toml_value(values[key])}")
    return Settings(config), sources


def resolve(host: str, root: Path = ROOT, local: Path | None = None) -> dict:
    """Merged config for HOST: the defaults, then every file in its chain."""
    return resolve_with_sources(host, root, local)[0]


def init(host: str, source: Path = ROOT, path: Path | None = None) -> str | None:
    """HOST's resolved config written to PATH; the change line, or None if unchanged."""
    if not (source / "hosts" / f"{host}.toml").is_file():
        raise ConfigError(f"no hosts/{host}.toml in {source}")
    path = path or local_path()
    text = (
        f"# This machine's config: hosts/{host}.toml and everything it extends,\n"
        f"# resolved by `dotfiles init` from {source.resolve()}.\n"
        "# apply, deploy, config and render read it; the next init overwrites it.\n\n"
    ) + tomli_w.dumps(resolve(host, source))
    if path.is_file() and path.read_text() == text:
        return None
    why = "content differs" if path.exists() else "missing"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return f"-> {shown(path)} ({why})"


def toml_value(value) -> str:
    # Arrays joined by hand: tomli-w breaks long ones over several lines.
    """VALUE as it is written in TOML, on one line."""
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return tomli_w.dumps({"v": value}).removeprefix("v = ").removesuffix("\n")


def explain(host: str, root: Path = ROOT, local: Path | None = None) -> str:
    """One line per leaf, `key = value  # file`: valid TOML, and grep finds any key."""
    config, sources = resolve_with_sources(host, root, local)
    return "".join(
        f"{key} = {toml_value(value)}  # {sources[key]}\n" for key, value in leaves(config)
    )


def check(root: Path = ROOT) -> dict[str, str | None]:
    """Resolve every host in hosts/ and one that is not there: host -> error or None."""
    results: dict[str, str | None] = {}
    for host in sorted(p.stem for p in (root / "hosts").glob("*.toml")) + ["unknown-host"]:
        try:
            resolve(host, root)
            results[host] = None
        except ConfigError as e:
            results[host] = str(e)
    return results
