"""Host configuration: defaults.toml, then the host's chain of profiles and hosts."""

import copy
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class ConfigError(Exception):
    pass


def load(path: Path, root: Path) -> dict:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path.relative_to(root)}: {e}") from None


def resolve(host: str, root: Path = ROOT) -> dict:
    """Merged config for HOST."""
    return copy.deepcopy(load(root / "defaults.toml", root))
