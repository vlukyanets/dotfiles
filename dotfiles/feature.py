"""The base class of every feature and the lookup of its strategy."""

from contextlib import AbstractContextManager, nullcontext

from dotfiles.platforms import Platform


class Feature:
    """What a feature does everywhere is its apply(); what differs per
    platform, its packages first of all, is a nested class named after the
    platform class (Arch, Linux, …), which apply() receives as its strategy."""

    def __init__(self, cfg: dict):
        self.cfg = cfg  # the resolved config

    def apply(self, strategy: Platform) -> None:
        """What this feature does, through STRATEGY for what is platform's."""

    def session(self, system: Platform) -> AbstractContextManager:
        """A context around the whole apply of an enabled feature: entered
        before the platform's setup, left after the last feature, after a
        failure or Ctrl-C too. Nothing by default."""
        return nullcontext()

    def strategy(self, system: Platform) -> Platform | None:
        """The nested class for SYSTEM's platform, walking up its class
        hierarchy (Arch, then Linux), combined with SYSTEM's class so it has
        every platform method; None when this feature has none for it."""
        for base in type(system).__mro__:
            nested = getattr(type(self), base.__name__, None)
            if isinstance(nested, type) and not issubclass(nested, Platform):
                name = f"{type(self).__name__}.{nested.__name__}"
                return type(name, (nested, type(system)), {})(self.cfg)
        return None
