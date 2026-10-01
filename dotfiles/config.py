"""Host configuration: the defaults, then the host's chain of profiles and hosts."""

import tomllib
from pathlib import Path
from typing import NamedTuple

import tomli_w

from dotfiles.errors import ConfigError
from dotfiles.layout import Layout, local_config, shown

# TOML's names, so an error reads like the file the user is editing.
_KINDS = {
    bool: "boolean",
    int: "integer",
    float: "float",
    str: "string",
    list: "array",
    dict: "table",
}


class Checks(NamedTuple):
    """What the schema's types cannot say, from the code that reads the keys.

    RULES: dotted key -> (test, what it must be), checked on the merged config.
    TYPES: dotted key -> the types it takes, where its default's type does not
    say: a key of several types, the default's first, or one with no default,
    in the resolved config only when a file sets it.
    """

    rules: dict[str, tuple]
    types: dict[str, tuple[type, ...]]


# No rules and no types: the entry points pass the features'.
_NO_CHECKS = Checks({}, {})


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
        raise MissingKey(f"{self._dotted}{key}: no such key in {Layout.DEFAULTS}")

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


def _kind(value) -> str:
    """VALUE's TOML type, as errors name it."""
    return _KINDS.get(type(value), type(value).__name__)


def _validate(data: dict, schema: dict, types: dict, where: str, prefix: str = "") -> None:
    """Every key of DATA in SCHEMA at the same path or in TYPES, of the type they give it."""
    for key, value in data.items():
        dotted = prefix + key
        if key not in schema and dotted not in types:
            raise ConfigError(f"{where}: {dotted}: unknown key")
        want = schema.get(key)
        kinds = types.get(dotted, (type(want),))
        # type() rather than isinstance(): a bool is an int to isinstance.
        if type(value) not in kinds:
            must = " or ".join(_KINDS[t] for t in kinds)
            raise ConfigError(f"{where}: {dotted}: must be {must}, got {_kind(value)}")
        if isinstance(want, dict):
            _validate(value, want, types, where, dotted + ".")


def merge_over(want: dict, base: dict) -> dict:
    """BASE with WANT merged over it: tables recursively, scalars and arrays replaced."""
    out = dict(base)
    for key, value in want.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            value = merge_over(value, base[key])
        out[key] = value
    return out


def chain(host: str, root: Path) -> list[tuple[str, dict]]:
    """HOST's files, each (path, data), parents before children; [] for an unknown host."""
    layout = Layout(root)
    order: list[tuple[str, dict]] = []
    done: set[Path] = set()

    def visit(path: Path, stack: list[Path]) -> None:
        """PATH's parents, then PATH itself, each once; fail on a cycle."""
        if path in stack:
            names = [p.stem for p in stack[stack.index(path) :] + [path]]
            raise ConfigError(f"extends: cycle {' → '.join(names)}")
        if path in done:
            return
        where = str(path.relative_to(root))
        data = load(path, root)
        parents = data.pop("extends", [])
        if not isinstance(parents, list) or not all(isinstance(p, str) for p in parents):
            raise ConfigError(f"{where}: extends: must be an array of strings")
        for parent in parents:
            try:
                found = layout.named(parent)
            except ConfigError as e:
                raise ConfigError(f"{where}: extends: {e}") from None
            if found is None:
                raise ConfigError(f"{where}: extends: no profile or host {parent!r}")
            visit(found, stack + [path])
        done.add(path)
        order.append((where, data))

    path = layout.named(host)
    if path is not None and path.is_relative_to(layout.hosts):
        visit(path, [])
    return order


def _leaves(data: dict, prefix: str = ""):
    """(dotted key, value) for every non-table value; arrays are leaves."""
    for key, value in data.items():
        if isinstance(value, dict):
            yield from _leaves(value, prefix + key + ".")
        else:
            yield prefix + key, value


def resolve_with_sources(
    host: str,
    root: Path = Layout.root,
    local: Path | None = None,
    source: Path | None = None,
    *,
    checks: Checks = _NO_CHECKS,
) -> tuple[dict, dict[str, str]]:
    """HOST's merged, validated config and the file each key comes from.

    The schema comes from ROOT, the checkout of the code that reads it; HOST
    from LOCAL, else from hosts/ of SOURCE (default this checkout). CHECKS
    come from the caller: entry points pass feature.checks().
    """
    schema = load(Layout(root).defaults, root)
    config = schema
    sources = {key: Layout.DEFAULTS for key, _ in _leaves(schema)}
    if local is None:
        files = chain(host, source or root)
    elif local.is_file():
        files = [(shown(local), load(local, root))]
    else:
        raise ConfigError(
            f"no {shown(local)} — run dotfiles init <host>, or pass --source <checkout>"
        )
    for where, data in files:
        _validate(data, schema, checks.types, where)
        config = merge_over(data, config)
        sources.update((key, where) for key, _ in _leaves(data))
    values = dict(_leaves(config))
    for key, (test, what) in checks.rules.items():
        if key in values and not test(values[key]):
            raise ConfigError(f"{host}: {key}: must be {what}, got {_toml_value(values[key])}")
    return Settings(config), sources


def resolve(
    host: str,
    root: Path = Layout.root,
    local: Path | None = None,
    source: Path | None = None,
    *,
    checks: Checks = _NO_CHECKS,
) -> dict:
    """Merged config for HOST: the defaults, then every file in its chain."""
    return resolve_with_sources(host, root, local, source, checks=checks)[0]


def init(
    host: str,
    root: Path = Layout.root,
    path: Path | None = None,
    source: Path | None = None,
    *,
    checks: Checks = _NO_CHECKS,
) -> str | None:
    """HOST of SOURCE (default this checkout) resolved and written to PATH; the change line, or None."""
    source = source or root
    found = Layout(source).named(host)
    if found is None or not found.is_relative_to(Layout(source).hosts):
        raise ConfigError(f"no host {host!r} in {source}/hosts")
    path = path or local_config()
    text = (
        f"# This machine's config: {found.relative_to(source)} and everything it extends,\n"
        f"# resolved by `dotfiles init` from {source.resolve()}.\n"
        "# apply, deploy, config and render read it; the next init overwrites it.\n\n"
    ) + tomli_w.dumps(resolve(host, root, source=source, checks=checks))
    if path.is_file() and path.read_text() == text:
        return None
    why = "content differs" if path.exists() else "missing"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return f"-> {shown(path)} ({why})"


def _toml_value(value) -> str:
    # Arrays joined by hand: tomli-w breaks long ones over several lines.
    """VALUE as it is written in TOML, on one line."""
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    return tomli_w.dumps({"v": value}).removeprefix("v = ").removesuffix("\n")


def explain(
    host: str,
    root: Path = Layout.root,
    local: Path | None = None,
    source: Path | None = None,
    *,
    checks: Checks = _NO_CHECKS,
) -> str:
    """One line per leaf, `key = value  # file`: valid TOML, and grep finds any key."""
    config, sources = resolve_with_sources(host, root, local, source, checks=checks)
    return "".join(
        f"{key} = {_toml_value(value)}  # {sources[key]}\n" for key, value in _leaves(config)
    )


def check(
    root: Path = Layout.root, source: Path | None = None, *, checks: Checks = _NO_CHECKS
) -> dict[str, str | None]:
    """Resolve every host in hosts/ of SOURCE and one that is not there: host -> error or None."""
    source = source or root
    results: dict[str, str | None] = {}
    for host in Layout(source).host_names() + ["unknown-host"]:
        try:
            resolve(host, root, source=source, checks=checks)
            results[host] = None
        except ConfigError as e:
            results[host] = str(e)
    return results
