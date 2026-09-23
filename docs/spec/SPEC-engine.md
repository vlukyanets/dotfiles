# Spec: `engine` — the `lib.sh` port and `dotfiles apply`

Status: approved 2026-09-24. Module of the [capability map](CAPABILITY-MAP.md);
depends on `config` (and `render` for the deploy step of `apply`).

## Objective

Port the old repo's shared library (`.chezmoitemplates/lib.sh`) to Python
and replace chezmoi's script runner with `dotfiles apply`. Features become
Python modules that call `ensure_*` helpers. The contract stays the same:
every check reads live state without root, a mutation goes through
`as_root` only when needed, and a machine that already matches prints
nothing and asks for no password.

`dotfiles apply` does, for this machine:

1. Resolve the config (no `init`, no `config_hash`: `check_config` is gone).
2. Run the enabled `before` features in order.
3. Deploy the dotfiles (`render.deploy`).
4. Run the enabled `after` features.
5. Print the notices collected along the way.

Out of scope: the package helpers (`ensure_pkg`, `ensure_aur`,
`ensure_replaced`, `ensure_rustup` go to `packages`) and every feature but
one sample, `nobeep`, which proves the runner end to end (the rest go to
`features`).

## Tech Stack

Stdlib only: `subprocess`, `shutil`, `os`, `pwd`/`grp`, `platform`
(`freedesktop_os_release`), `importlib`, `tempfile`, `re`. No new dependency.

## `lib.sh` → `dotfiles/engine.py`

| `lib.sh` | here | notes |
|---|---|---|
| `log` | `print` | |
| `warn MSG` | `warn(msg)` | `warning: MSG` on stderr |
| `die MSG` | `die(msg)` | raises `Failed`: the step fails (see Failures) |
| `changed MSG` | `changed(msg)` | counts, prints `-> MSG` |
| `notice MSG` | `notice(msg)` | prints now, kept in memory, replayed at the end |
| `need CMD` | `shutil.which` | |
| `require CMD...` | dropped | used once; `shutil.which(...) or die(...)` |
| `os_guard NAME...` | `os_guard(*names)` | raises `Skip`; the runner ends the feature silently |
| `as_root CMD...` | `as_root(*cmd)` | see Root |
| `_writable` | `_writable(path)` | same walk up to the first existing parent |
| `ensure_file SRC DST [MODE [OWNER]]` | `ensure_file(dst, content, mode=0o644, owner=None)` | content (str or bytes) instead of a temp file, so the heredoc + `$_tmp` pattern goes away |
| `ensure_symlink TARGET LINK` | `ensure_symlink(target, link)` | |
| `ensure_line FILE REGEX LINE` | `ensure_line(file, regex, line)` | Python `re` instead of awk's ERE; the two scripts that use it are ported with it |
| `ensure_absent_line FILE REGEX` | dropped | no script uses it; returns when a feature needs it |
| `ensure_service UNIT [--user]` | `ensure_service(unit, user=False)` | |
| `ensure_sysctl KEY VALUE` | `ensure_sysctl(key, value)` | |
| `ensure_gsetting SCHEMA KEY VALUE` | `ensure_gsetting(schema, key, value)` | |
| `ensure_group_member GROUP` | `ensure_group_member(group)` | checks the group database (`grp`), not `id -nG` (see Decisions) |
| `fetch URL DST` | dropped | no script uses it |
| `retry CMD...` | `retry(fn, *args)` | `retry(as_root, "pacman", "-Sy")`; three attempts, 10 s and 20 s apart; returns `False` if all three fail |
| `defer MSG` | `defer(msg)` | raises `Deferred`; the runner turns it into the notice `MSG (network?) — the next apply retries` and goes on |
| `CHANGES`, `before=$CHANGES` | `ensure_*` return `True` when they changed something | `if ensure_file(...): as_root("systemctl", "reload", ...)` |
| `OS`, `DISTRO`, `DISTRO_LIKE` | read once from `sys.platform` and `/etc/os-release` | |
| `_tmp`, traps | a `with` block per helper; `finally` in the runner | |

For command output there is one more helper, `output(*cmd) -> str | None`:
it returns stdout without the trailing newline whatever the exit status
(`systemctl is-enabled` prints `disabled` and exits 1), or `None` when the
command is not installed. Checks use it; it never mutates anything.

### Helper contracts

Every helper checks first. If nothing differs it returns `False` and prints
nothing. Otherwise it mutates, calls `changed(...)` and returns `True`.
The `->` lines are the ones from `lib.sh`:

```
-> /etc/modprobe.d/nobeep.conf (missing)          ensure_file: missing / content differs / mode 600 / owner a:b
-> /etc/localtime -> /usr/share/zoneinfo/UTC       ensure_symlink
-> fstrim.timer enabled and started (was disabled/inactive)
-> sysctl vm.swappiness = 10
-> gsettings org.gnome.desktop.interface color-scheme = 'prefer-dark'
-> added valentinl to group docker                 + notice to log out and back in
```

- `ensure_file` compares without root. It writes as the user when the path
  is writable and the owner is the user (or not given); otherwise it writes
  through `as_root install -D -m MODE [-o U -g G]` from a private temp file.
  As before, a root-only file the user cannot read looks different every
  time: features keep root files world-readable.
- `ensure_line` and `ensure_sysctl` keep the mode and owner of the file they
  edit.
- `ensure_service`: `is-enabled` and `is-active` run first. `enabled` or
  `static`/`alias`/`indirect` units that are not active get `start`;
  anything else gets `enable --now`. `user=True` uses `--user` and no root.

### Root

`as_root(*cmd)` runs `SUDO_CMD` (default `sudo`, split with `shlex`; empty
means no prefix) followed by the command. It adds no prefix when the process
already runs as root. When `DOTFILES_SNAPPER_STATE` is set, sudo gets
`--preserve-env=SNAP_PAC_SKIP,DOTFILES_SNAPPER_STATE`. The command must
succeed (`check=True`): a failed mutation fails the feature.

`sudo` prompts on its own when its timestamp has expired. A clean apply
never gets that far.

### Dry run

`dotfiles apply --dry-run`: every helper checks and prints its `->` line
as usual, but skips the mutation. `as_root`, `run` (the user-level
`subprocess.run` for mutations, e.g. `git clone`, `gsettings set`) and
`render.deploy` do nothing. No sudo is ever called. A check that depends on
an earlier change in the same run sees the state as it is, so a dry run can
report more than a real run would, never less.

### `SYSROOT`

`engine.SYSROOT` (default `/`) is prefixed to every path a helper touches.
The tests set it to a temp dir (autouse, like `HOME`), so a feature can be
run against an empty tree. It is not a command-line option.

## `dotfiles apply` — `dotfiles/apply.py`

```python
class Step(NamedTuple):
    module: str  # dotfiles/features/<module>.py
    gate: str | None  # runs only when features.<gate>.enabled
    needs: tuple[str, ...] = ()  # earlier steps that must not have failed


BEFORE = [
    Step("nobeep", "nobeep"),
    ...,
    # e.g., in `packages`: Step("paru", "aur", needs=("makepkg",))
]
AFTER = [...]
```

- The order is this list. It keeps the old groups (core, packages,
  system, shell, ssh, desktop) and order.
- A step with a gate runs only when `features.<gate>.enabled`. A disabled
  step is never imported, so it prints nothing and has no side effects.
  `None` is for the few modules that read several flags themselves (the
  old map scripts: services, tools, apps).
- `needs` names earlier steps (in `BEFORE` or, for an `after` step, in
  either list) that this one builds on. A test checks that every name
  exists and comes earlier. The actual edges are decided per feature in
  `packages` and `features`; this module provides the mechanism.
- A feature module is one function:

```python
"""Silence the PC speaker."""

from dotfiles.engine import ensure_file, os_guard


def apply(cfg: dict) -> None:
    os_guard("arch")
    ensure_file("/etc/modprobe.d/nobeep.conf", "blacklist pcspkr\n", owner="root:root")
```

  `cfg` is the whole resolved config; a feature reads its settings from
  `cfg["features"]["<name>"]`.
- With `features.snapper` enabled, `apply` sets `SNAP_PAC_SKIP=y` and
  `DOTFILES_SNAPPER_STATE=$XDG_RUNTIME_DIR/dotfiles-snapper` in its own
  environment for the whole run. This replaces chezmoi's `[scriptEnv]`.
  The snapshot features themselves belong to `features`.
- stdout is line-buffered, so `->` lines and the output of child
  commands appear in order.

### Failures

- `Skip` (`os_guard`): the feature ends silently.
- `Deferred` (`defer`): the feature ends, and its notice is kept.
- Any other exception (`die`, a failed `as_root`, a bug): the step
  failed. The runner prints `error: <step>: <message>` to stderr and
  continues with the next step, the deploy and the `after` steps.
- A step whose `needs` include a failed step is not run and counts as
  failed itself, so what depends on it is not run either:
  `error: paru: not run, makepkg failed`. A need that is disabled,
  skipped by `os_guard` or deferred does not block: only a failure does.
- `apply` exits 1 at the end when any step failed or was not run.
- Ctrl-C stops the run, replays the notices, and exits 130.
- Notices are printed at the end in every case, after a failure too:

```
Notices from this apply:
    added to group docker — log out and back in for it to take effect
```

  The notices file in `$XDG_RUNTIME_DIR` and the "left over from an
  earlier apply" replay are gone: there is one process, and its `finally`
  replaces the trap. A run killed with SIGKILL loses its notices.

## Commands

```
uv run dotfiles apply --dry-run     # what would change; no sudo, no writes
uv run dotfiles apply               # this machine: features, dotfiles, after steps, notices
uv run pytest tests/test_engine.py tests/test_apply.py
```

`deploy` stays as a separate command for the dotfiles alone.

## Project Structure

```
dotfiles/engine.py        output, notices, as_root, retry/defer, os_guard, ensure_* helpers
dotfiles/apply.py         BEFORE/AFTER, the runner, snapper env, notices at the end
dotfiles/features/        one module per feature (nobeep only, in this module)
tests/test_engine.py      helpers, twice each: one change, then none
tests/test_apply.py       runner: order, gates, failures, notices, dry run
```

## Code Style

Same as `config` and `render`: plain functions, comments explain why,
messages name the file, unit or key. A feature reads top to bottom like
its bash script did:

```python
def apply(cfg: dict) -> None:
    os_guard("arch")
    locale = cfg["features"]["locale"]
    # A list, not any(generator): every line must be ensured, not just up to the first change.
    edits = [ensure_line("/etc/locale.gen", f"^#?{re.escape(l)}$", l) for l in locale["locales"]]
    if any(edits):
        as_root("locale-gen")
```

## Testing Strategy

This replaces `ci/test-lib.sh`; its checks all carry over.

- Every mutating helper is called twice on paths the test user owns under
  `SYSROOT`: `True` then `False`, one `->` line then none. Mode and owner
  of an edited file are kept. Owner tests use the test user's own
  `user:group`, since tests never become root.
- Every external command goes through one function, `engine._run(argv,
  ...)`. Tests replace it (monkeypatch) with a Python fake that answers
  checks (`systemctl is-enabled`, `sysctl -n`, `gsettings get`, …) from a
  dict and records every call. A test asserts which calls were made and
  that the second run makes none. No stub scripts, no shell.
- `as_root`: the argv it builds with `SUDO_CMD` set, with and without the
  snapper variable, and as root. With the default `SUDO_CMD=false` from
  `conftest.py`, a helper that really tried to escalate fails the test.
- `retry` (sleep patched), `defer`, `os_guard` against a fake os-release,
  `notice` (printed immediately and at the end).
- Runner (fake feature modules in a temp package): order, gated steps
  not imported, `Skip` silent, a failed step does not stop the steps that
  do not need it, a step that needs it is not run (transitively), exit 1,
  notices after a failure, dry run makes no call to sudo or `run`.
- `nobeep` in an empty `SYSROOT`: dry run reports `(missing)`, and a real
  run with `SUDO_CMD=""` and no owner writes the file and is then silent.
- `dotfiles apply --dry-run` on hyper-lin is checked by hand, not in CI.

## Boundaries

- **Always:** check before mutating. Mutate only through `as_root`, `run`
  or a helper. Every helper respects dry run and `SYSROOT`. Tests stay in
  temp dirs with `SUDO_CMD=false`.
- **Ask first:** changing the failure policy, adding a dependency, a
  helper that deletes.
- **Never:** shell scripts: features, helpers and tests are Python, and
  commands are run as argv lists, never through a shell. Call sudo in a
  dry run or a test; touch `../__dotfiles`; keep sudo alive in the
  background.

## Success Criteria

1. Each helper that is ported: first call changes one thing, second call
   none. The rows of the table above that say "dropped" are the only
   `lib.sh` helpers without a Python counterpart.
2. `dotfiles apply --dry-run` on this machine runs end to end without
   sudo. On a machine that matches, `dotfiles apply` prints nothing.
3. A step that fails prints `error: <step>: …`. The steps that need it
   are not run; the others still run, notices are still printed, and the
   exit code is 1.
4. pytest, ruff and `dotfiles check` are green locally and in CI.

## Decisions

1. **A failed step blocks only the steps that need it** (chezmoi stopped
   at the first failed script). A broken feature, such as a download
   that failed, no longer blocks the dotfiles and every unrelated
   feature after it; the steps that build on it (`needs`) are not run,
   so they do not fail again with a confusing second error.
2. **Helpers return whether they changed something** instead of
   features comparing a global counter; there is no counter.
3. **`ensure_group_member` reads the group database.** `id -nG` only
   sees the change after the next login, so every apply until then ran
   `usermod` again, printed a change and repeated the notice.
4. **Notices live in memory**, since one process runs the whole apply.
5. **Dropped:** `require`, `fetch`, `ensure_absent_line` (unused),
   `check_config` and `config_hash` (the config is resolved on every
   run).
