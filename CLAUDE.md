# CLAUDE.md

Maintainer guide. `README.md` is the entry point for humans; `docs/spec/`
holds the capability map and the module specs that drive the work.

## Commands

| Task | Command |
|---|---|
| Tests | `uv run --isolated --group dev pytest` |
| Lint and format | `uv run --isolated --group dev ruff check . && uv run --isolated --group dev ruff format --check .` |
| Every host resolves | `uv run --isolated dotfiles check` |
| This machine's config | `uv run --exact dotfiles init [host]` writes `~/.config/dotfiles/config.toml`; commands read it unless `--source <checkout>` or `--host` |
| One host, with sources | `uv run --exact dotfiles config --host <name> --explain` |
| A host's home tree | `uv run --exact dotfiles render --host <name> --out <empty dir>` |
| Dotfiles into `$HOME` | `uv run --exact dotfiles deploy --dry-run`, then without the flag |
| Features + dotfiles | `uv run --exact dotfiles apply --dry-run`, then without the flag |

CI (`.github/workflows/ci.yml`) runs the first three on every push to
master and every PR; uv is pinned there by version and sha256.

## Navigation

- Keys and defaults: `dotfiles/defaults.toml` — the schema; a new key goes here first.
  A feature is `features.<name>.enabled` plus its settings in the same table.
- Profiles `profiles/`, machines `hosts/`; one namespace for `extends`. A
  machine runs from `~/.config/dotfiles/config.toml` (`config.init`,
  `layout.local_config`); the CLI (`dotfiles/cli.py`) picks it or a checkout.
- Where things are: `dotfiles/layout.py` — `Layout(root)` names a checkout's
  paths (`defaults`, `hosts`, `profiles`, `home`, `home_toml`, `system`),
  `named(name)` a host or profile by bare name (ambiguous → error) or by
  path under `hosts/`, which nests folders; `local_config()` this machine's
  config, `shown(path)` a path with `~`; code asks it, never joins
  `root / "hosts"` itself.
- Resolution, validation, merge, explain, check: `dotfiles/config.py`; it
  imports no feature: the entry points pass `checks=feature.checks()`.
  `ConfigError` lives in `dotfiles/errors.py`, for every layer.
- Dotfiles: `home/` (real names, `*.j2` templates), modes and gates in
  `home.toml`, rendering in `dotfiles/render.py`.
- Files features write outside `$HOME`: templates under `system/` at their
  path from `/`, rendered by `render.template` and written with `files.ensure`.
- Helpers the same on every system: `dotfiles/engine.py` (`Report`,
  `Shell`, `Files` in a `Machine`, passed from `apply()` to the platform
  as `self.report`, `self.shell`, `self.files`, and reached by every
  feature through `self.system`; `current()` only for entry points),
  retries in `dotfiles/retry.py`, the root process in `dotfiles/root.py`.
- Platforms: a package each, `dotfiles/platforms/<name>/`, that shares
  nothing with the others: its `OperatingSystem` subclass (`ArchLinuxOs`
  in `arch/_os.py`, with the os-release `id` it runs on, `detect` in
  `platforms/discovery.py` matches ID then ID_LIKE), its package manager
  (`arch/_pacman.py`: `Pacman`) and its `features/`. The one base is
  `linux/` (`LinuxOs`: systemd, sysctl, groups, gsettings, and features for
  every Linux); a platform runs Linux's feature where it has none of that name.
- Features: `platforms/<name>/features/<feature>.py`, one `Feature`
  subclass each, named after the module (`packaging` → `Packaging`), built
  with its table `features.<feature>` as `self.settings` and the platform
  as `self.system`; checks the types cannot make are its `rules` and
  `either`. It declares its packages (`packages()`, from the
  repositories), the ones they replace (`replaces()`) and the features it
  needs (`requires()`: enabled, or check fails; run first), then does the
  rest in `apply()`. The name gates it; the order comes from the package
  graph and those requirements (`dotfiles/plan.py`; `dotfiles/apply.py`
  runs it). Nothing else is
  declared. The schema in `defaults.toml` is shared by every platform.
- Why: `docs/spec/SPEC-<module>.md`, then `docs/spec/CAPABILITY-MAP.md`.

## Commits and branches

- `master` holds finished modules; each module is built on its own branch.
- Branch names are short, lowercase, hyphenated and say what changes
  (`nvidia-driver-installation`); no generated names or `claude/` prefixes.
- Subject: one line, imperative, plain language. Body: optional, one paragraph.
- No Conventional Commits prefixes, no AI attribution lines in commits or
  pull requests.
- pytest and ruff pass before every commit; the spec changes with the code.

## Pitfalls

- A name no other module uses starts with `_` (functions, constants,
  classes, methods), and so does a module nothing outside its package
  imports (`arch/_os.py`); no `__all__`. Tests may still reach a `_name`.
- `__init__.py` only imports from its own submodules, never defines a
  class; ruff's F401 is off there, so no `X as X`.
- A platform class is `<Name>Os` (`ArchLinuxOs`, `LinuxOs`).
- `type(v) is type(want)`, not `isinstance`: TOML `true` would pass as an
  integer otherwise.
- Every test runs with `HOME` and the XDG directories in pytest's temp dir,
  an active `engine.Machine` whose sysroot is a temp dir, and `SUDO_CMD=false` (`tests/conftest.py`,
  autouse). Root goes only through `shell.run` inside `with shell.as_root():`, which
  reads `SUDO_CMD`, so a test can never prompt for a password or change
  the machine.
- A feature mutates only through its system's `files`, `shell.run` or a
  platform method: they respect dry run and the sysroot. Commands are argv lists, never
  a shell; tests fake commands with `conftest.Fake.install`, which sets
  the shell's `execute` and `root`, not with scripts.
- Templates: a tag alone on its line vanishes with its newline
  (trim_blocks, lstrip_blocks). Booleans print as `True` in Jinja: write
  `{{ x | lower }}` where the file needs `true`.
- A `.keep` that only holds a directory in git is gated off with
  `when = "false"` in `home.toml`, so no empty file lands in `$HOME`.
