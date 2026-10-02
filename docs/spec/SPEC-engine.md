# Spec: `engine` — helpers, platforms and `dotfiles apply`

Status: draft 2026-09-24, revises the version approved the same day
(platforms, features as classes, order from the package graph and each
feature's requirements); platforms in directories of their own 2026-09-29. Module of
the [capability map](CAPABILITY-MAP.md); depends on `config`.

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
3. Run the features, each after the features whose packages its own
   packages depend on.
4. Print the notices collected along the way.

Out of scope: installing from the repositories (`packages`), and every
feature, `packaging`, `reflector`, `rustup`, `paru` (the AUR) and
`no_beep` included (`features`).

## Tech Stack

Stdlib only: `subprocess`, `shutil`, `os`, `pwd`/`grp`, `platform`
(`freedesktop_os_release`), `importlib`, `pkgutil`, `abc`,
`contextvars`, `dataclasses`, `tempfile`, `re`, `socket` and
`multiprocessing.connection` (the root process). No new dependency.

## Project Structure

```
dotfiles/engine.py                     Report, Shell, Files, Machine; die, defer; current()
dotfiles/retry.py                      RetryPolicy, Attempt, retrying()
dotfiles/root.py                       the root process: runs what the shell sends, stdlib only
dotfiles/platforms/discovery.py        detect(), platforms(), every(), named(); __init__.py is empty
dotfiles/platforms/operating_system.py OperatingSystem (abstract): id, machine, package manager
dotfiles/platforms/package_manager.py  PackageManager (abstract): depends from direct()
dotfiles/platforms/linux/_os.py        LinuxOs(OperatingSystem): systemd, sysctl, groups, gsettings
dotfiles/platforms/linux/features/     features every Linux runs the same, the fallback
dotfiles/platforms/arch/_os.py         ArchLinuxOs(LinuxOs), id "arch", with Pacman
dotfiles/platforms/arch/_pacman.py     Pacman(PackageManager)
dotfiles/platforms/arch/features/      Arch's features, one per file
dotfiles/feature.py                    Feature; classes(platform), every(), checks()
dotfiles/plan.py                       Step, steps(), requirements(), order(), cycles()
dotfiles/apply.py                      the runner, check()
dotfiles/errors.py                     ConfigError, raised by every layer
tests/test_engine.py                   Shell, Files, Report, retries
tests/test_platforms.py                LinuxOs and Pacman against a fake shell
tests/test_apply.py                    plan and runner with a fake platform and fake features
```

## `dotfiles/engine.py` — the same on every system

The engine is four classes, one instance each per apply:

- `Report`: what the apply prints, `warn`, `changed`, `notice`,
  `flush` (the notices again, at the end), and `printed`, whether it
  printed a change or a warning.
- `Shell(dry_run, execute, root)`: `output`, `run`, `as_root`. EXECUTE runs
  every command (`subprocess.run` by default), ROOT every one that needs
  root (`root(sudo, argv, **kwargs)`, the root process by default); tests
  pass fakes for both (`conftest.Fake.install`).
- `Files(shell, report, sysroot)`: `path`, `ensure`, `line`, `symlink`,
  under SYSROOT.
- `Machine(dry_run, sysroot, execute, root)` holds the three.

The machine is passed, never looked up: `apply()` builds one,
`engine.current().fresh(dry_run)` (the same system and commands, a new
report), and hands it to the platform (`OperatingSystem(machine)`),
which gives it to its package manager and to every feature. A platform
has `self.shell`, `self.files` and `self.report`.
`current()` is read only by entry points (`apply()`, `requirements()`):
it is the machine of the enclosing `with machine.active():` (a
`ContextVar`; the tests' temp one), else `engine._REAL`.

| Call | Does |
|---|---|
| `die(msg)` | raises `Failed`: the feature fails (see Failures) |
| `defer(msg)` | raises `Deferred`; the runner turns it into the notice `MSG (network?) — the next apply retries` and goes on |
| `report.warn(msg)` | `warning: MSG` on stderr |
| `report.changed(msg)` | prints `-> MSG`: the only kind of line a clean apply never prints |
| `report.notice(msg)` | `warning: MSG` now, kept in memory, replayed at the end |
| `shell.output(*cmd)` | stdout without the trailing newline, whatever the exit status (`systemctl is-enabled` prints `disabled` and exits 1); `None` when the command is not installed. For checks only |
| `shell.run(*cmd)` | a mutation (`git clone`, `pacman -S`); must succeed. As the user, or as root inside `shell.as_root()` |
| `with shell.as_root():` | every `run` in the block runs as root; see Root |
| `for attempt in retrying(report, policy):` / `with attempt:` | the block again on failure, as often and as late as the `RetryPolicy` says; see Retries |
| `files.ensure(dst, content, mode=0o644, owner=None)` | DST has CONTENT (str or bytes), MODE and OWNER (`"user:group"`) |
| `files.symlink(target, link)` | LINK points to TARGET |
| `files.line(file, regex, line, before=None)` | the first line matching REGEX (Python `re`) becomes LINE, else LINE goes before the line matching BEFORE, or at the end |

Every `files` method checks first. If nothing differs it returns `False`
and prints nothing. Otherwise it mutates, calls `report.changed(...)` and
returns `True`, so a feature reacts to a change with
`if self.files.ensure(...): ...`.

- `files.ensure` compares without root. It writes as the user when the path
  is writable (the file itself, and the nearest existing directory above
  it) and the owner is the user (or not given); otherwise it writes
  through `as_root install -D -m MODE [-o U -g G]` from a private temp file.
  A root-only file the user cannot read looks different every time:
  features keep root files world-readable.
- `files.line` keeps the mode and owner of the file it edits. A file the
  user cannot read fails the feature (`not readable without root`).
- `engine.differs(path, data, mode, owner=None)` is the comparison
  `files.ensure` makes: `missing`, `content differs`,
  `mode 644`, `owner …`, or `None`.

### Root

```python
with self.shell.as_root():
    self.shell.run("systemctl", "enable", "--now", unit)
```

Inside `as_root()`, `run` goes through `SUDO_CMD` (default `sudo`, split
with `shlex`; empty means none); none when the process already runs as
root. The first such `run` starts one root process,
`SUDO_CMD python -I dotfiles/root.py SOCKET`: sudo asks for the password
once, and every root command of the shell after it goes over that unix
socket (in a private temp dir) as `(argv, kwargs)` and comes back as the
`CompletedProcess` or the exception `subprocess.run` raised. The command
inherits the terminal's stdout and stderr, so its output shows as before;
its stdin is a pipe closed at once (EOF). sudo's `use_pty` (default since
1.9.14) keeps the user's terminal in raw mode for as long as the command
runs while stdin is that terminal, and every line the apply prints would
step down the screen; a pipe (not `/dev/null`) makes sudo leave it alone.
The password is still read from `/dev/tty`. The process exits
when the shell hangs up (at exit, or when the apply dies); if it cannot
start (`SUDO_CMD=false`, a wrong password) the `run` raises
`CalledProcessError`. That is the shell's ROOT; a test's fake gets the
prefix and the command (`root(sudo, argv)`) and starts nothing. The block sets a flag on the `Shell`
and puts the previous value back on exit, so blocks nest. Only mutations get root:
`output()` runs as the user inside the block too, so a check never asks
for a password. `files.ensure` and `files.symlink` choose root themselves
(the path is not writable, or another owner); `as_root()` around them
forces it. The command must
succeed (`check=True`): a failed mutation fails the feature. A clean
apply never gets that far, so never asks for a password.

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
    retry_on: tuple[type[Exception], ...] = (CalledProcessError,)


_NETWORK = RetryPolicy()  # 3 attempts, 10 s then 20 s apart: the default

for attempt in retrying(self.report):
    with attempt:
        self.shell.run("git", "clone", url, tmp)
        self.shell.run("makepkg", "-si", cwd=tmp)
```

- `dotfiles/retry.py`: `retrying(report, policy=_NETWORK)`, its warnings
  into REPORT, each attempt an `Attempt`; a call that needs other numbers
  makes its own: `retrying(report, RetryPolicy(attempts=5, delay=2))`.
- The whole block is the unit: a failure anywhere in it runs it again from
  the top, so it must be safe to repeat (clone into a fresh temp dir, not
  into the destination).
- A failure of a type in `retry_on` that is not the last attempt prints
  `warning: git clone … failed (attempt 1/3), retrying in 10s` (the
  command from the exception), sleeps and lets the loop go on; the loop
  ends at the first success. Any other exception propagates at once.
- The last failure propagates: the feature fails, or a feature that can
  wait catches it and calls `defer(...)`.
- Combines with root: `with attempt, self.shell.as_root():`.
- Only what goes to the network goes in the block: a failure that repeats
  (a file conflict, a missing program) must not cost the waits. pacman
  downloads with `-Sw`/`-Syuw` in the block and installs after it, once.
- Tests pass `RetryPolicy(delay=0)`, or patch `retry.sleep`.

### Dry run

`dotfiles apply --dry-run`: every check runs and every `->` line is
printed, but no mutation: `run` (with or without root) does nothing,
and sudo is never called. A check that depends on an earlier change in the
same run sees the state as it is, so a dry run can report more than a real
run would, never less.

### The sysroot

The machine's `Files.sysroot` (default `/`) is prefixed to every path a
`files` method touches; `files.path(name)` is where to read NAME. The tests make
a `Machine` with a temp dir (autouse, like `HOME`), so a feature can be
run against an empty tree. It is not a command-line option.

## Platforms — `dotfiles/platforms/`

A platform is a package, `platforms/<name>/`, that shares nothing with
the others but `linux/`, their base: its `OperatingSystem` subclass in
`_os.py`, named `<Name>Os`, its package manager and its `features/`.
`__init__.py` only imports what the rest of the code uses (`ArchLinuxOs`,
`Pacman`); a module nothing outside imports starts with `_`. Features call
the platform; they never run a package manager or systemctl themselves.

Every class here is instantiated once per apply: a platform with the
machine alone, a feature with its own table of the resolved config
(`self.settings`) and the platform; methods are instance methods
and take no config argument.
Static methods and classes used as mere namespaces are avoided.

```python
class PackageManager(ABC):  # package_manager.py: one per apply, shared by every feature
    def setup(self) -> None: ...  # ready to install; once per apply
    @abstractmethod
    def missing(self, names: list[str]) -> list[str]: ...  # not installed; no root
    @abstractmethod
    # One transaction, REPLACES removed first; returns what it has not, for build().
    def install(self, names: list[str], replaces: Sequence[str] = ()) -> list[str]: ...
    def build(self, names: list[str]) -> None: ...  # Pacman: the AUR; fails by default
    @abstractmethod
    def upgrade(self) -> None: ...  # full upgrade, databases synced; never a partial one
    @abstractmethod
    def direct(self, names: list[str]) -> dict[str, set[str]]: ...  # direct dependencies
    def provides(self, names: list[str]) -> dict[str, set[str]]: ...  # other names; none by default
    def depends(self, names: list[str]) -> dict[str, set[str]]: ...  # transitive, cached


class OperatingSystem(ABC):  # operating_system.py
    id: ClassVar[str] = ""  # the os-release ID it runs on; a base has none
    manager_class: type[PackageManager]  # abstract until a platform names one

    def __init__(self, machine: Machine):
        self.machine = machine  # and its shell, files, report as attributes
        self.manager = self.manager_class(machine)


class LinuxOs(OperatingSystem):  # linux/_os.py: what every Linux here shares
    def ensure_service(self, unit: str, user: bool = False) -> bool: ...
    def ensure_sysctl(self, key: str, value) -> bool: ...
    def ensure_gsetting(self, schema: str, key: str, value: str) -> bool: ...
    def ensure_group_member(self, group: str) -> bool: ...


class Pacman(PackageManager):  # arch/_pacman.py
    ...  # missing: -T; install: -Rdd, -Si, -Sw, -S; direct, provides: -Si, else -Qi; upgrade: -Syuw, -Su


class ArchLinuxOs(LinuxOs):  # arch/_os.py
    id = "arch"
    manager_class = Pacman
```

- `detect(machine)` reads `/etc/os-release`: the platform is the
  concrete `OperatingSystem` subclass whose `id` is ID, else the first of
  ID_LIKE that one has (`cachyos` → `arch`), instantiated with
  `machine`. `platforms()` imports every package of `platforms/` and
  lists those classes; none → `apply` fails: `error: no platform for fedora`.
- The `ensure_*` methods check first and return whether they changed, like `files`:
  - `ensure_service`: `is-enabled` and `is-active` first; `enabled` or
    `static`/`alias`/`indirect` units that are not active get `start`,
    anything else `enable --now`. `user=True` uses `--user` and no root.
  - `ensure_sysctl`: `files.line` on `/etc/sysctl.d/99-dotfiles.conf`,
    then live through `sysctl -qw` when `sysctl -n` differs.
  - `ensure_gsetting`: VALUE in GVariant text form; nothing without
    gsettings.
  - `ensure_group_member`: read from the group database (`grp`), not
    `id -nG`, which changes only at the next login; adds a notice to log
    out and back in. A group that does not exist is an error; a dry run
    does not get that far while the package that brings it is missing.
- `Pacman.direct` answers from the sync database without root;
  `PackageManager.depends` walks it and caches per apply, so a new
  platform's manager says only what a package depends on directly.
- A feature reaches its system's manager (`self.system.manager`), and
  with it the cache.

## Features — `dotfiles/feature.py`, `platforms/<name>/features/`

A feature is a class per platform: `platforms/arch/features/docker.py`
holds Arch's `Docker`, `platforms/debian/features/docker.py` Debian's.
They share no code; what is the same on every Linux is one module in
`platforms/linux/features/`, which a platform runs where it has none of
that name.

```python
"""Docker with the applying user in its group."""

from dotfiles.feature import Feature


class Docker(Feature):  # platforms/arch/features/docker.py
    def packages(self):
        return ["docker", "docker-buildx", "docker-compose"]

    def apply(self):
        self.system.ensure_service("docker.service")
        self.system.ensure_group_member("docker")
```

- `feature.classes(platform)` walks the platform's class hierarchy from
  the base down (`LinuxOs`, then `ArchLinuxOs`), each class's package's
  `features/`, so the platform's own module of a name wins. Modules
  starting with `_` are helpers, not features. The runner builds each with
  `(settings, system)`: `features.docker` of the resolved config and the
  platform, reaching `ensure_service`, its package manager and the machine
  through `self.system`, and calls `apply()`. A feature sees its own
  table only; the rest of the config does not reach it.
- A feature with no module for this platform, nor on Linux, does not apply
  to this machine and is skipped.
- A feature in `linux/features/` runs on every platform below `LinuxOs`,
  so it uses only what `LinuxOs` and the base `PackageManager` have
  (`self.system.manager.upgrade()`, not a `Pacman` method); what needs
  more goes in the platform's own `features/`.
- `packages()`, `replaces()` and `requires()` default to `[]`, `apply()`
  to nothing. They read `self.settings`, so a list can depend on settings
  (the nvidia driver, the languages).
- What the schema's types cannot check about a feature's keys is its
  `rules` (key under `features.<name>` → `(test, what it must be)`), and
  the types of a key with several or with no default are its `types`. `feature.checks()` gathers
  both from every feature of every platform (the schema is one) into a
  `config.Checks`, and the entry points (`cli`, `apply`) pass it to
  `config` as `checks=`: config never imports features. Without it only
  the types are checked.
- Every platform has its own package names; nothing maps one onto
  another, and a platform may need packages the others do not.
- The feature's name is its file name: it runs only when
  `features.<name>.enabled`. A feature whose table has no `enabled`
  (`packaging`) cannot be turned off and runs always; so does a file whose
  name is not a feature in the schema, and reads its flags itself
  (services, tools, apps).
- A feature may declare the features it needs on its platform,
  `requires()` (default `[]`), with the reason next to it:

  ```python
  class Paru(Feature):  # platforms/arch/features/paru.py
      def requires(self):
          return ["packaging", "rustup"]  # makepkg's MAKEFLAGS; cargo
  ```

  Each must run, enabled or without an `enabled`: otherwise `steps()` raises `ConfigError`, one
  `paru: requires features.rustup.enabled = true` per requirement
  (`paru: requires x, which is not a feature` for a name the schema
  lacks), so `apply` stops before setup. A cycle of requirements is the
  same kind of error, one line per cycle (`gaming → nvidia → gaming: each
  requires the next, so none can run first`). `dotfiles check` asks
  `requires()` of every feature that would run, on every platform
  (`discovery.every`), so a host that breaks one fails check wherever it
  would run. `requires()` reads `self.settings` only, never the machine.
  Requirements are for what the package graph cannot see: a config that
  starts another feature's program, a config another feature writes
  (`packaging`'s makepkg drop-in for paru), a program a feature installs
  in place of a package (cargo from `rustup`), a virtual dependency a
  feature chooses (`jdk` for kotlin). A required feature runs first.
- Nothing else is declared: no gate, no order but through `requires()`.

## `dotfiles apply` — `dotfiles/plan.py`, `dotfiles/apply.py`

1. **Platform.** `system = detect(machine)`, an instance of the platform
   class, then `system.manager.setup()`, on every apply (it checks first;
   the base one does nothing, and `Pacman` has none of its own).
2. **Packages.** The packages of every enabled feature that applies here,
   together: `manager.missing(...)`, and when something is missing, one
   line `-> packages: a b c (missing)` and `manager.install(...)` in one
   transaction, whose order is the package manager's, what the features
   `replaces()` removed first. What install() returns, not in the
   repositories, is built at its feature's turn. Nothing missing →
   nothing printed, no root.
3. **Features, in order;** each first gets the packages install() left,
   built with `manager.build(...)` (the AUR on Arch), a failure its own.
   Feature A runs before feature B when B
   requires A, or when a package of B needs a package that A has and B
   does not, by `manager.depends(...)` on all their packages (a package
   both list, like `git`, orders neither). A dependency on a name that a
   package provides (`java-runtime`, `manager.provides(...)`) is one on
   that package. Features free to run at the same point run by
   name, and a feature without packages has no edges. Features whose
   packages need each other in a cycle get a place by name but do not
   run: one `error: glvnd, graphics: not run, they need each other:
   glvnd → graphics → glvnd`, and the features after them are not run as
   after any failure.
   Each runs as `Docker(settings, system).apply()` does.
4. **Notices.**

stdout is line-buffered, so `->` lines and the output of child commands appear in
order.

### Failures

- `setup` fails (`error: platform: …`, nothing is installed) or
  `install` fails after its retries (`error: packages: …`): every feature
  with a package still missing afterwards is not run (`error: docker: not
  run, packages missing: docker-buildx`); the others run. The next apply
  finds the packages still missing and tries again.
- A feature raises (`die`, a failed `run`, a bug): `error: <feature>:
  <message>` on stderr; the features whose packages need its packages, or
  that require it, are not run (`error: foo: not run, docker failed`), and so on transitively.
  The others run.
- The message (`apply._describe`) keeps the words of a failure the code
  reports (`die`, `ConfigError`). Anything else says what went wrong and
  the innermost line of our code that raised it, past the stdlib, the
  installed packages, `engine.py`, `retry.py` and `config.py`, so a failed `run` or a
  missing key points at the feature's line:
  - a failed command: ``error: cmd: `pacman -S x` failed with exit status
    1, at dotfiles/platforms/arch/features/x.py:12: self.shell.run("pacman", "-S", "x")``;
  - a key the schema lacks: `error: packaging: features.packaging.pacmen:
    no such key in dotfiles/defaults.toml, at …`;
  - a bug: `error: div: unexpected ZeroDivisionError (division by zero),
    at …`.
- `defer` in a feature: it ends, its notice is kept, nothing is blocked.
- `apply` exits 1 when any feature failed or was not run. Ctrl-C stops the
  run, replays the notices and exits 130 (`128 + signal.SIGINT`); so does
  every other command, and the root process. Notices are printed at the
  end in every case, from the runner's `finally`.
- In a dry run the runner does not call `install`. A feature with a
  package still missing, or running after such a feature, is not checked
  (its checks would only see what is not there yet): `-> docker (after
  its packages)`. Every other feature runs its checks and reports what
  the real run would change.

```
Notices from this apply:
    added to group docker — log out and back in for it to take effect
```

## Commands

```
uv run --exact dotfiles apply --dry-run     # what would change; no sudo, no writes
uv run --exact dotfiles apply               # this machine: packages, features, notices
uv run --isolated --group dev pytest tests/test_engine.py tests/test_platforms.py tests/test_apply.py
```

## Code Style

Same as `config`: plain functions where there is one
implementation, classes where platforms differ; comments explain why;
messages name the file, unit or key. A feature reads top to bottom:

```python
class Locale(Feature):  # platforms/linux/features/locale.py: glibc is always there
    def apply(self):
        locale = self.settings
        # A list, not any(generator): every line must be ensured, not just up to the first change.
        edits = [
            self.system.files.line("/etc/locale.gen", f"^#?{re.escape(l)}$", l)
            for l in locale["locales"]
        ]
        if any(edits):
            with self.system.shell.as_root():
                self.system.shell.run("locale-gen")
```

## Testing Strategy

- `Files` methods: called twice on paths the test user owns under
  `SYSROOT`: `True` then `False`, one `->` line then none.
- Every external command goes through the machine's `Shell.execute`, or
  `Shell.root` as root; tests set both to a Python fake that answers
  checks from a dict and records every call. No stub scripts, no shell.
- Platforms: `LinuxOs.ensure_*` like the `Files` methods; `Pacman`
  against canned `pacman -T` / `pacman -Si` output: missing, one install
  call with every name, the transitive graph. `detect()` against fake
  os-release files: ID, ID_LIKE, none.
- Features: a platform's own module of a name wins over its base's, the
  base's runs where the platform has none; the feature reaches the
  platform as `system`; a module without the class of its name → an error.
- Runner (a fake platform whose features are a temp package): one install
  for all packages and silence when none is missing; order from the fake
  graph, ties by name; a requirement runs first; a requirement left off is a
  `ConfigError` from `apply` and `requirements`; a failed feature blocks
  exactly the features whose packages need its packages or that require
  it; missing packages block their feature;
  notices after a failure and on Ctrl-C; a dry run never calls sudo.
- `dotfiles apply --dry-run` on a real host with every feature on runs
  checks only and never calls sudo.

## Boundaries

- **Always:** check before mutating; mutate only through the machine's
  `shell.run`, a `files` method or a platform method; respect dry run and `SYSROOT`; tests in
  temp dirs with `SUDO_CMD=false`.
- **Ask first:** changing the failure policy; a dependency; a helper that
  deletes; a platform besides Arch.
- **Never:** shell scripts (features, helpers, platforms and tests are
  Python; commands are argv lists, never a shell); sudo in a dry run or a
  test; a root process outliving the apply; writing an order by hand,
  or a requirement the package graph already covers.

## Success Criteria

1. A feature file holds only what it does and, per platform, its
   packages and the features it requires; nothing orders or gates it but
   its name, the package graph and those requirements.
2. A second platform is one directory in `platforms/`, its class and its
   features; nothing of another platform changes.
3. On a machine that matches, `dotfiles apply` prints only `nothing to
   change` and runs no sudo; `--dry-run` never runs sudo.
4. A failed feature blocks only the features whose packages need its
   packages or that require it; exit 1; notices still printed.
5. pytest, ruff and `dotfiles check` are green locally and in CI.

## Decisions

1. **Order and dependencies come from the package manager**, through
   `PackageManager.depends`, plus what a feature `requires()`: what the graph
   cannot see (a config that starts another feature's program, a setup
   part, a provider chosen by another feature) is declared per platform,
   where it holds, and checked against the host's config. Order the graph does
   not cover is fixed by the phases: the package manager is ready before
   any install (`setup`). No dotfiles are deployed outside the features
   (2026-10-02): a dotfile is a feature's file, ordered like the rest.
2. **Platforms are directories that do not intersect.** A platform does
   with its own tools what differs between systems, and its features are
   its own: a feature is written per platform, not as shared code with a
   part per platform, so a change for Debian cannot break Arch. What is
   truly common lives in `linux/`, the one base, as helpers on `LinuxOs`
   and fallback features.
3. **Package names are per platform**, never mapped.
4. **All packages in one transaction**, before any feature runs: one
   check, one sudo, and the package manager orders the installation.
5. **A failed feature blocks only what builds on it**, in the package
   graph or by requirement; the rest of the apply goes on.
6. **`files` and `ensure_*` return whether they changed something**; the engine only
   remembers whether the apply printed a change or a warning, so a run
   that printed neither and failed nothing ends with `nothing to change`
   instead of no output at all. **Notices live in memory**, since one
   process runs the whole apply.
7. **One object per concern, one machine per apply.** `Report`, `Shell`
   and `Files` in engine, the package manager apart from the platform,
   the features apart from both, and `apply.Apply`
   with a method per phase. The machine is passed in, from `apply()` to
   the platform, its package manager and every feature; only entry
   points read `current()`, and nothing is a module global a test or
   `apply` has to reset.
8. **No helper deletes** a line or a file yet; one comes with the first
   feature that needs it.
