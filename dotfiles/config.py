"""Host configuration: defaults.toml, then the host's chain of profiles and hosts."""

import copy
import tomllib
from pathlib import Path

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


def resolve(host: str, root: Path = ROOT) -> dict:
    """Merged config for HOST: the defaults, then its file in hosts/ if it has one."""
    schema = load(root / "defaults.toml", root)
    config = copy.deepcopy(schema)
    path = root / "hosts" / f"{host}.toml"
    if path in (root / "hosts").glob("*.toml"):
        data = load(path, root)
        validate(data, schema, str(path.relative_to(root)))
        merge(config, data)
    if config.get("secrets", {}).get("backend", "none") not in SECRETS_BACKENDS:
        raise ConfigError(
            f"{host}: secrets.backend: must be one of {', '.join(SECRETS_BACKENDS)},"
            f" got {config['secrets']['backend']!r}"
        )
    return config
