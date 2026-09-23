"""Host configuration: defaults.toml, then the host's chain of profiles and hosts."""

import copy
import tomllib
from pathlib import Path

import tomli_w

ROOT = Path(__file__).resolve().parent.parent

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


class ConfigError(Exception):
    pass


def load(path: Path, root: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.relative_to(root)}: {e}") from None


def kind(value) -> str:
    return KINDS.get(type(value), type(value).__name__)


def validate(data: dict, schema: dict, where: str, prefix: str = "") -> None:
    """Every key of DATA exists in SCHEMA at the same path, with the same type."""
    for key, value in data.items():
        dotted = prefix + key
        if key not in schema:
            raise ConfigError(f"{where}: {dotted}: unknown key")
        want = schema[key]
        # type() rather than isinstance(): a bool is an int to isinstance.
        if type(value) is not type(want):
            raise ConfigError(f"{where}: {dotted}: must be {kind(want)}, got {kind(value)}")
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
    """(file, data) for HOST and every file it extends, parents first.

    Depth-first, post-order, each file once: a shared ancestor is merged at
    its first position, so a later parent does not reset what an earlier one
    set on top of it.
    """
    known = names(root)
    order: list[tuple[str, dict]] = []
    done: set[str] = set()

    def visit(name: str, stack: list[str]) -> None:
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

    # The host itself only comes from hosts/: a machine called "server" does
    # not pick up the server profile by accident.
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


def resolve_with_sources(host: str, root: Path = ROOT) -> tuple[dict, dict[str, str]]:
    """Merged config for HOST and, per dotted key, the file its value came from."""
    schema = load(root / "defaults.toml", root)
    config = copy.deepcopy(schema)
    sources = {key: "defaults.toml" for key, _ in leaves(schema)}
    for where, data in chain(host, root):
        validate(data, schema, where)
        merge(config, data)
        sources.update((key, where) for key, _ in leaves(data))
    if config.get("secrets", {}).get("backend", "none") not in SECRETS_BACKENDS:
        raise ConfigError(
            f"{host}: secrets.backend: must be one of {', '.join(SECRETS_BACKENDS)},"
            f" got {config['secrets']['backend']!r}"
        )
    return config, sources


def resolve(host: str, root: Path = ROOT) -> dict:
    """Merged config for HOST: the defaults, then every file in its chain."""
    return resolve_with_sources(host, root)[0]


def toml_value(value) -> str:
    # Arrays joined by hand: tomli-w breaks long ones over several lines.
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(v) for v in value) + "]"
    return tomli_w.dumps({"v": value}).removeprefix("v = ").removesuffix("\n")


def explain(host: str, root: Path = ROOT) -> str:
    """One line per leaf, `key = value  # file`: valid TOML, and grep finds any key."""
    config, sources = resolve_with_sources(host, root)
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
