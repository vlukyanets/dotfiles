"""The base class of every feature and the lookup of its strategy."""

from dotfiles.platforms.operating_system import Platform


class Strategy:
    """What a feature's nested platform class declares; each default is nothing."""

    def packages(self) -> list[str]:
        """A strategy's packages on this platform, in its own names."""
        return []

    def replaces(self) -> list[str]:
        """Installed packages a strategy's packages() replace, removed just before the install."""
        return []

    def requires(self) -> list[str]:
        """Features a strategy needs: enabled, or check fails; they run first."""
        return []


class Feature:
    """A feature: its settings in cfg, its strategies as nested platform classes."""

    def __init__(self, cfg: dict):
        """The feature with the resolved CFG."""
        self.cfg = cfg  # the resolved config

    def apply(self, strategy: Platform) -> None:
        """What this feature does, through STRATEGY for what is platform's."""

    def strategy(self, system: Platform) -> Platform | None:
        """The nested class for SYSTEM's platform, or its nearest base, mixed into SYSTEM; None if none."""
        for base in type(system).__mro__:
            nested = getattr(type(self), base.__name__, None)
            if isinstance(nested, type) and not issubclass(nested, Platform):
                name = f"{type(self).__name__}.{nested.__name__}"
                mixed = type(name, (nested, Strategy, type(system)), {})
                return mixed(self.cfg, system.manager)  # SYSTEM's, with its cache
        return None
