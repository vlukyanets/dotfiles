# Spec: `engine` — helpers, platforms and `dotfiles apply`

Status: draft 2026-09-24, revises the version approved the same day
(platforms, features as classes, order from the package graph). Module of
the [capability map](CAPABILITY-MAP.md); depends on `config` (and `render`
for the deploy step of `apply`).

## Objective

The helpers features are written with, the platforms that carry out what
differs between systems, and `dotfiles apply`, which runs them. The
contract: every check reads live state without root, a mutation goes
through root only when needed, and a machine that already matches
prints only `nothing to change` and asks for no password.

Nobody writes down dependencies. A feature says which packages it needs on
each platform; the platform's package manager says how those packages
depend on each other; the order of the features follows from that.

`dotfiles apply` does, for this machine:

1. Detect the platform from os-release and let it prepare its package
   manager.
2. Install the packages of every enabled feature, in one transaction.
3. Deploy the dotfiles (`render.deploy`).
4. Run the features, each after the features whose packages its own
   packages depend on.
5. Print the notices collected along the way.

Out of scope: the Arch package manager's setup (pacman.conf drop-ins,
mirrors, reflector), the AUR and paru (all `packages`), and every feature
but one sample, `nobeep` (the rest go to `features`).

## Tech Stack

Stdlib only: `subprocess`, `shutil`, `os`, `pwd`/`grp`, `platform`
(`freedesktop_os_release`), `importlib`, `pkgutil`, `abc`,
`contextvars`, `dataclasses`, `tempfile`, `re`. No new dependency.

## Project Structure

```
dotfiles/engine.py             output, notices, dry run, run, as_root(), retrying(), defer,
                               ensure_file/line/symlink: the same on every system
dotfiles/platforms/__init__.py Platform (abstract), detect()
dotfiles/platforms/linux.py    Linux(Platform): systemd, sysctl, groups, gsettings
dotfiles/platforms/arch.py     Arch(Linux): pacman — missing, install, depends
dotfiles/feature.py            Feature, the base class of every feature; strategy lookup
dotfiles/features/<name>.py    one feature per file, flat
dotfiles/apply.py              the runner
tests/test_engine.py           shared helpers
tests/test_platforms.py        Linux and Arch against a fake _run
tests/test_apply.py            the runner with a fake platform and fake features
```

## `dotfiles/engine.py` — the same on every system

| Helper | Does |
|---|---|
| `warn(msg)` | `warning: MSG` on stderr |
| `die(msg)` | raises `Failed`: the feature fails (see Failures) |
| `changed(msg)` | prints `-> MSG`: the only kind of line a clean apply never prints |
| `notice(msg)` | prints now, kept in memory, replayed at the end |
| `output(*cmd)` | stdout without the trailing newline, whatever the exit status (`systemctl is-enabled` prints `disabled` and exits 1); `None` when the command is not installed. For checks only |
| `run(*cmd)` | a mutation (`git clone`, `pacman -S`); must succeed. As the user, or as root inside `as_root()` |
| `with as_root():` | every `run` in the block runs as root; see Root |
| `for attempt in retrying(policy):` / `with attempt:` | the block again on failure, as often and as late as the `RetryPolicy` says; see Retries |
| `defer(msg)` | raises `Deferred`; the runner turns it into the notice `MSG (network?) — the next apply retries` and goes on |
| `ensure_file(dst, content, mode=0o644, owner=None)` | DST has CONTENT (str or bytes), MODE and OWNER (`"user:group"`) |
| `ensure_symlink(target, link)` | LINK points to TARGET |
| `ensure_line(file, regex, line)` | the first line matching REGEX (Python `re`) becomes LINE, appended when none does |

Every helper checks first. If nothing differs it returns `False` and prints
nothing. Otherwise it mutates, calls `changed(...)` and returns `True`, so
a feature reacts to a change with `if ensure_file(...): ...`.

- `ensure_file` compares without root. It writes as the user when the path
  is writable (the file itself, and the nearest existing directory above
  it) and the owner is the user (or not given); otherwise it writes
  through `as_root install -D -m MODE [-o U -g G]` from a private temp file.
  A root-only file the user cannot read looks different every time:
  features keep root files world-readable.
- `ensure_line` keeps the mode and owner of the file it edits.

### Root

```python
with as_root():
    run("systemctl", "enable", "--now", unit)
```

Inside `as_root()`, `run` puts `SUDO_CMD` (default `sudo`, split with
`shlex`; empty means no prefix) before the command; no prefix when the
process already runs as root. The block sets a `ContextVar`, so blocks
nest and the previous value comes back on exit. Only mutations get root:
`output()` runs as the user inside the block too, so a check never asks
for a password. `ensure_file` and `ensure_symlink` choose root themselves
(the path is not writable, or another owner); `as_root()` around them
forces it. When `SNAP_PAC_SKIP` is set (by `features.snapper`), sudo gets
`--preserve-env=SNAP_PAC_SKIP`. The command must
succeed (`check=True`): a failed mutation fails the feature. `sudo`
prompts on its own when its timestamp has expired; a clean apply never
gets that far.

### Retries

For anything that goes to the network. A `with` block runs once, so the
attempts are a loop and each one is a block. How often and how long to
wait is a `RetryPolicy`:

```python
@dataclass(frozen=True)
class RetryPolicy:
    attempts: int = 3  # in total, the first one included
    delay: float = 10  # seconds before the second attempt
    backoff: float = 2  # each next delay is the previous one times this
    max_delay: float = 60  # no single wait longer than this
    retry_on: tuple[type[Exception], ...] = (CalledProcessError, OSError)


NETWORK = RetryPolicy()  # 3 attempts, 10 s then 20 s apart

for attempt in retrying(NETWORK):
    with attempt:
        run("git", "clone", url, tmp)
        run("makepkg", "-si", cwd=tmp)
```

- `retrying(policy=NETWORK)`; a call that needs other numbers makes its
  own: `retrying(RetryPolicy(attempts=5, delay=2))`, or
  `dataclasses.replace(NETWORK, attempts=5)`.
- The whole block is the unit: a failure anywhere in it runs it again from
  the top, so it must be safe to repeat (clone into a fresh temp dir, not
  into the destination).
- A failure of a type in `retry_on` that is not the last attempt prints
  `warning: git clone … failed (attempt 1/3), retrying in 10s` (the
  command from the exception), sleeps and lets the loop go on; the loop
  ends at the first success. Any other exception propagates at once.
- The last failure propagates: the feature fails, or a feature that can
  wait catches it and calls `defer(...)`.
- Combines with root: `with attempt, as_root():`.
- Tests pass `RetryPolicy(delay=0)`; nothing patches `sleep`.

### Dry run

`dotfiles apply --dry-run`: every check runs and every `->` line is
printed, but no mutation: `run` (with or without root) and `render.deploy` do nothing,
and sudo is never called. A check that depends on an earlier change in the
same run sees the state as it is, so a dry run can report more than a real
run would, never less.

### `SYSROOT`

`engine.SYSROOT` (default `/`) is prefixed to every path a helper touches.
The tests set it to a temp dir (autouse, like `HOME`), so a feature can be
run against an empty tree. It is not a command-line option.

## Platforms — `dotfiles/platforms/`

A platform is a class that does, with its own tools, what differs between
systems. Features call it; they never run a package manager or systemctl
themselves.

Every class here, platforms, features and strategies, is instantiated once
per apply with the resolved config (`__init__(self, cfg)`, kept as
`self.cfg`); methods are instance methods and take no config argument.
Static methods and classes used as mere namespaces are avoided.

```python
class Platform(ABC):
    def __init__(self, cfg: dict):
        self.cfg = cfg  # the resolved config

    def setup(self) -> None: ...  # the package manager ready; once per apply

    def packages(self) -> list[str]:
        return []  # a strategy's default

    def replaces(self) -> list[str]:
        return []  # installed packages its packages replace (packages spec)

    @abstractmethod
    def missing(self, names: list[str]) -> list[str]: ...  # not installed; no root
    @abstractmethod
    def install(self, names: list[str], replaces: list[str] = ()) -> None: ...  # one transaction
    # name -> every package it needs, transitively
    @abstractmethod
    def depends(self, names: list[str]) -> dict[str, set[str]]: ...


class Linux(Platform):  # linux.py: what every Linux here shares
    def ensure_service(self, unit: str, user: bool = False) -> bool: ...
    def ensure_sysctl(self, key: str, value) -> bool: ...
    def ensure_gsetting(self, schema: str, key: str, value: str) -> bool: ...
    def ensure_group_member(self, group: str) -> bool: ...


class Arch(Linux):  # arch.py
    ...  # missing: pacman -T; install: pacman -S or paru; depends: pacman -Si, walked
```

- `detect(cfg)` reads `/etc/os-release`: the platform is the class in
  `platforms/<ID>.py`, else in `platforms/<first of ID_LIKE that has a
  file>.py`, instantiated with `cfg`. No file → `apply` fails:
  `error: no platform for fedora`.
- The `ensure_*` methods keep the contracts they have as helpers:
  - `ensure_service`: `is-enabled` and `is-active` first; `enabled` or
    `static`/`alias`/`indirect` units that are not active get `start`,
    anything else `enable --now`. `user=True` uses `--user` and no root.
  - `ensure_sysctl`: `ensure_line` on `/etc/sysctl.d/99-dotfiles.conf`,
    then live through `sysctl -w` when `sysctl -n` differs.
  - `ensure_gsetting`: VALUE in GVariant text form; nothing without
    gsettings.
  - `ensure_group_member`: read from the group database (`grp`), not
    `id -nG`, which changes only at the next login; adds a notice to log
    out and back in. A group that does not exist is an error, except in
    a dry run: its package, which a dry run does not install, brings it.
- `Arch.depends` answers from the sync database without root and caches
  per apply.

## Features — `dotfiles/feature.py`, `dotfiles/features/`

A feature is a class. What it does everywhere is its `apply`; what differs
per platform, its packages first of all, is a strategy: a nested class
named after the platform class, which `apply` receives as an object.

```python
"""Docker with the applying user in its group."""

from dotfiles.feature import Feature


class Docker(Feature):
    def apply(self, strategy):
        strategy.ensure_service("docker.service")
        strategy.ensure_group_member("docker")

    class Arch:
        def packages(self):
            return ["docker", "docker-buildx", "docker-compose"]

    class Debian:
        def packages(self):
            return ["docker.io", "docker-buildx-plugin", "docker-compose-plugin"]
```

- The runner picks the strategy by walking the platform's class
  hierarchy: on Arch `Docker.Arch`, else `Docker.Linux`. It builds the
  strategy's class from that nested class and the detected platform class
  (`Docker.Arch` + `platforms.Arch`), so the strategy has every platform
  method (`ensure_service`, …) and whatever the feature adds or overrides
  for that platform. The runner creates `Docker(cfg)` and the strategy
  with the same `cfg`, and calls `docker.apply(strategy)`.
- A feature with no strategy for this platform does not apply to this
  machine and is skipped silently.
- `packages()` defaults to `[]` (on `Platform`); `apply` to nothing.
  Both read `self.cfg`, the whole resolved config, so a list can depend on
  settings (the nvidia driver, the languages). A step that differs per platform
  beyond packages is one more method on the strategies, called by `apply`.
- Every platform has its own package names; nothing maps one onto
  another, and a platform may need packages the others do not.
- The feature's name is its file name: it runs only when
  `features.<name>.enabled`. A file whose name is not a feature in the
  schema runs always and reads its flags itself (services, tools, apps).
- Nothing else is declared: no gate, no dependencies, no order.

## `dotfiles apply` — `dotfiles/apply.py`

1. **Platform.** `system = detect(cfg)`, an instance of the platform
   class, then `system.setup()`, on every apply (it checks first).
2. **Packages.** The packages of every enabled feature that applies here,
   together: `system.missing(...)`, and when something is missing, one
   line `-> packages: a b c (missing)` and `system.install(...)` in one
   transaction, whose order is the package manager's. Nothing missing →
   nothing printed, no root.
3. **Dotfiles.** `render.deploy`.
4. **Features, in order.** `system.depends(...)` on all their packages
   gives the graph: feature A runs before feature B when a package of B
   needs a package that A has and B does not (a package both list, like
   `git`, orders neither). Features free to run at the same point run by
   name, and a feature without packages has no edges. A cycle in the
   package graph is broken by name, not an error: its features need each
   other and any order is as good.
   Each runs as `Docker(cfg).apply(strategy)` does.
5. **Notices.**

Phases 1–4 run inside the `session(system)` of every enabled feature, a
context manager that is `nullcontext()` unless the feature needs to wrap
the apply (`snapper` does, for its snapshot pair). The sessions are left
after a failure and on Ctrl-C too. Inside them, `with
platforms.watching(hook):` has HOOK called right before each package
change; a platform calls `platforms.transaction()` before every command
that installs, upgrades or removes a package (not on a dry run). stdout is
line-buffered, so `->` lines and the output of child commands appear in
order.

### Failures

- `setup` fails (`error: platform: …`, nothing is installed) or
  `install` fails after its retries (`error: packages: …`): every feature
  with a package still missing afterwards is not run (`error: docker: not
  run, packages missing: docker-buildx`); the others run. The next apply
  finds the packages still missing and tries again.
- A feature raises (`die`, a failed `run`, a bug): `error: <feature>:
  <message>` on stderr; the features whose packages need its packages are
  not run (`error: foo: not run, docker failed`), and so on transitively.
  The others run.
- `defer` in a feature: it ends, its notice is kept, nothing is blocked.
- `apply` exits 1 when any feature failed or was not run. Ctrl-C stops the
  run, replays the notices and exits 130. Notices are printed at the end
  in every case, from the runner's `finally`.
- In a dry run the runner does not call `install`, and step 4 runs every
  feature anyway: its checks report what the real run would change.

```
Notices from this apply:
    added to group docker — log out and back in for it to take effect
```

## Commands

```
uv run --exact dotfiles apply --dry-run     # what would change; no sudo, no writes
uv run --exact dotfiles apply               # this machine: packages, dotfiles, features, notices
uv run --isolated --group dev pytest tests/test_engine.py tests/test_platforms.py tests/test_apply.py
```

`deploy` stays as a separate command for the dotfiles alone.

## Code Style

Same as `config` and `render`: plain functions where there is one
implementation, classes where platforms differ; comments explain why;
messages name the file, unit or key. A feature reads top to bottom:

```python
class Locale(Feature):
    def apply(self, strategy):
        locale = self.cfg["features"]["locale"]
        # A list, not any(generator): every line must be ensured, not just up to the first change.
        edits = [
            ensure_line("/etc/locale.gen", f"^#?{re.escape(l)}$", l) for l in locale["locales"]
        ]
        if any(edits):
            with as_root():
                run("locale-gen")

    class Arch: ...  # glibc is always there: supported, no packages
```

## Testing Strategy

- Shared helpers: called twice on paths the test user owns under
  `SYSROOT`: `True` then `False`, one `->` line then none.
- Every external command goes through `engine._run(argv, ...)`; tests
  replace it with a Python fake that answers checks from a dict and
  records every call. No stub scripts, no shell.
- Platforms: `Linux.ensure_*` as the helpers are tested today; `Arch`
  against canned `pacman -T` / `pacman -Si` output: missing, one install
  call with every name, the transitive graph. `detect()` against fake
  os-release files: ID, ID_LIKE, none.
- Features: the strategy is picked through the platform's hierarchy
  (`Arch`, then `Linux`), has the platform's methods and the nested
  class's, and is what `apply` receives; none → skipped.
- Runner (a fake platform, fake features in a temp package): one install
  for all packages and silence when none is missing; order from the fake
  graph, ties by name; a failed feature blocks exactly the features whose
  packages need its packages; missing packages block their feature;
  notices after a failure and on Ctrl-C; a dry run never calls sudo.
- `nobeep` in an empty `SYSROOT`; `dotfiles apply --dry-run` on hyper-lin
  by hand.

## Boundaries

- **Always:** check before mutating; mutate only through `run`, a helper
  or a platform method; respect dry run and `SYSROOT`; tests in
  temp dirs with `SUDO_CMD=false`.
- **Ask first:** changing the failure policy; a dependency; a helper that
  deletes; a platform besides Arch.
- **Never:** shell scripts (features, helpers, platforms and tests are
  Python; commands are argv lists, never a shell); sudo in a dry run or a
  test; keeping sudo alive in the background; writing dependencies or
  order by hand.

## Success Criteria

1. A feature file holds only what it does and, per platform, its
   packages; nothing orders or gates it but its name and the package graph.
2. A second platform is one file in `platforms/` plus a nested class in
   the features it supports; no feature's shared code changes.
3. On a machine that matches, `dotfiles apply` prints only `nothing to
   change` and runs no sudo; `--dry-run` never runs sudo.
4. A failed feature blocks only the features whose packages need its
   packages; exit 1; notices still printed.
5. pytest, ruff and `dotfiles check` are green locally and in CI.

## Decisions

1. **Order and dependencies come from the package manager**, through
   `Platform.depends`; nothing is declared by hand. Order the graph does
   not cover is fixed by the phases: the package manager is ready before
   any install (`setup`), and the dotfiles are deployed before any
   feature.
2. **Platforms are classes; a feature gets its platform part as a
   strategy.** A platform does with its own tools what differs between
   systems; a feature's nested class per platform holds its packages and
   whatever else differs there, and `apply` receives it as an object
   rather than inheriting from it.
3. **Package names are per platform**, never mapped.
4. **All packages in one transaction**, before any feature runs: one
   check, one sudo, and the package manager orders the installation.
5. **A failed feature blocks only what builds on it** in the package
   graph; the rest of the apply goes on.
6. **Helpers return whether they changed something**; the engine only
   remembers whether the apply printed a change or a warning, so a run
   that printed neither and failed nothing ends with `nothing to change`
   instead of no output at all. **Notices live in memory**, since one
   process runs the whole apply.
7. **No helper deletes** a line or a file yet; one comes with the first
   feature that needs it.
