"""What an apply runs and in which order: the enabled features, their requirements, cycles."""

from typing import NamedTuple

from dotfiles import engine
from dotfiles.errors import ConfigError
from dotfiles.feature import Feature, classes
from dotfiles.platforms import discovery
from dotfiles.platforms.operating_system import OperatingSystem


class Step(NamedTuple):
    """One enabled feature on this platform, with what it installs and needs."""

    name: str  # the module's name, and the feature's in the schema
    feature: Feature
    packages: frozenset[str]
    replaces: frozenset[str]
    requires: frozenset[str] = frozenset()  # features that must be on, and run first


def _found(cfg: dict, system: OperatingSystem) -> list[Step]:
    """A Step per feature of SYSTEM's platform that CFG does not disable."""
    found = []
    for name, cls in classes(type(system)).items():
        if not cfg["features"].get(name, {}).get("enabled", True):  # no `enabled`: always on
            continue
        feature = cls(cfg["features"].get(name, {}), system)
        packages, replaces = frozenset(feature.packages()), frozenset(feature.replaces())
        found.append(Step(name, feature, packages, replaces, frozenset(feature.requires())))
    return found


def _problems(cfg: dict, found: list[Step]) -> list[str]:
    """What is wrong with the requirements of FOUND: unmet or cyclic, one line each."""
    requires = {step.name: step.requires for step in found}
    return _unmet(cfg, requires) + _circles(requires)


def steps(cfg: dict, system: OperatingSystem) -> list[Step]:
    """A Step per feature that runs on SYSTEM; fails if a requirement is unmet or cyclic."""
    found = _found(cfg, system)
    if problems := _problems(cfg, found):
        raise ConfigError("; ".join(problems))
    return found


def _unmet(cfg: dict, requires: dict[str, frozenset[str]]) -> list[str]:
    """What each feature REQUIRES that CFG does not enable, one line each."""
    problems = []
    for feature, names in sorted(requires.items()):
        for name in sorted(names):
            if name not in cfg["features"]:
                problems.append(f"{feature}: requires {name}, which is not a feature")
            elif not cfg["features"][name].get("enabled", True):
                problems.append(f"{feature}: requires features.{name}.enabled = true")
    return problems


def cycles(edges: dict[str, frozenset[str] | list[str]]) -> list[list[str]]:
    """Every cycle of EDGES (name -> names it needs), each once, from its smallest name."""
    found: dict[frozenset[str], list[str]] = {}
    done: set[str] = set()

    def visit(path: list[str]) -> None:
        """Walk on from the last name of PATH, recording each cycle back into it."""
        for name in sorted(edges.get(path[-1], ())):
            if name in path:
                cycle = path[path.index(name) :]
                first = cycle.index(min(cycle))
                found.setdefault(frozenset(cycle), cycle[first:] + cycle[:first])
            elif name not in done and name in edges:
                visit([*path, name])
        done.add(path[-1])

    for name in sorted(edges):
        if name not in done:
            visit([name])
    return sorted(found.values())


def circle(cycle: list[str]) -> str:
    """CYCLE as `a → b → a`."""
    return " → ".join([*cycle, cycle[0]])


def _circles(requires: dict[str, frozenset[str]]) -> list[str]:
    """Each cycle of REQUIRES, one line each: none of its features can run first."""
    return [f"{circle(c)}: each requires the next, so none can run first" for c in cycles(requires)]


def requirements(cfg: dict) -> None:
    """Fail if an enabled feature's requires() is unmet or cyclic on any platform: for check."""
    problems: list[str] = []
    for system in discovery.every(engine.current()):
        problems += [p for p in _problems(cfg, _found(cfg, system)) if p not in problems]
    if problems:
        raise ConfigError("; ".join(problems))


def order(
    steps: list[Step], depends: dict[str, set[str]], provides: dict[str, set[str]] | None = None
) -> list[tuple[Step, list[str]]]:
    """STEPS in run order, each with the features it runs after (packages and requires).

    A dependency on a name a package PROVIDES (java-runtime) is one on that package.
    """
    provides = provides or {}
    own = {
        step.name: {n for p in step.packages for n in (p, *provides.get(p, ()))} for step in steps
    }
    owners: dict[str, set[str]] = {}
    for step in steps:
        for name in own[step.name]:
            owners.setdefault(name, set()).add(step.name)
    names = {step.name for step in steps}
    after = {
        step.name: sorted(
            {
                owner
                for pkg in step.packages
                for dep in depends.get(pkg, ())
                if dep not in own[step.name]
                for owner in owners.get(dep, ())
            }
            | (step.requires & names)
        )
        for step in steps
    }
    todo = sorted(steps)
    done: list[tuple[Step, list[str]]] = []
    ran: set[str] = set()
    while todo:
        ready = [step for step in todo if ran.issuperset(after[step.name])]
        step = (ready or todo)[0]
        todo.remove(step)
        ran.add(step.name)
        done.append((step, after[step.name]))
    return done
