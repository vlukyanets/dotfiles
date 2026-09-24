# CLAUDE.md

Maintainer guide. `README.md` is the entry point for humans; `docs/spec/`
holds the capability map and the module specs that drive the work.

## Commands

| Task | Command |
|---|---|
| Tests | `uv run --isolated --group dev pytest` |
| Lint and format | `uv run --isolated --group dev ruff check . && uv run --isolated --group dev ruff format --check .` |
| Every host resolves | `uv run --isolated dotfiles check` |
| One host, with sources | `uv run --exact dotfiles config --host <name> --explain` |
| A host's home tree | `uv run --exact dotfiles render --host <name> --out <empty dir>` |
| Dotfiles into `$HOME` | `uv run --exact dotfiles deploy --dry-run`, then without the flag |
| Features + dotfiles | `uv run --exact dotfiles apply --dry-run`, then without the flag |

CI (`.github/workflows/ci.yml`) runs the first three on every push to
master and every PR; uv is pinned there by version and sha256.

## Navigation

- Keys and defaults: `dotfiles/defaults.toml` — the schema; a new key goes here first.
  A feature is `features.<name>.enabled` plus its settings in the same table.
- Profiles `profiles/`, machines `hosts/`; one namespace for `extends`.
- Resolution, validation, merge, explain, check: `dotfiles/config.py`.
- Dotfiles: `home/` (real names, `*.j2` templates), modes and gates in
  `home.toml`, rendering in `dotfiles/render.py`.
- Registries: `data/*.toml` (ssh keys, languages), merged into the template
  context; the names a host takes from them are checked in
  `render.registries` (`REFERENCES`).
- Helpers the same on every system: `dotfiles/engine.py`. What differs
  between systems: `dotfiles/platforms/<os-release ID>.py` (`Arch` on
  `Linux` on `Platform`).
- Features: `dotfiles/features/<name>.py`, one `Feature` subclass each; its
  nested classes (`Arch`, `Linux`, …) are the strategies `apply` receives,
  with the packages for that platform (`packages()`, repository and AUR
  alike) and the ones they replace (`replaces()`). The name gates it; the order comes
  from the package graph (`dotfiles/apply.py`). Nothing else is declared.
- Why: `docs/spec/SPEC-<module>.md`, then `docs/spec/CAPABILITY-MAP.md`.

## Commits and branches

- `master` holds finished modules; each module is built on its own branch.
- Subject: one line, imperative, plain language. Body: optional, one paragraph.
- No Conventional Commits prefixes, no AI attribution lines in commits or
  pull requests.
- pytest and ruff pass before every commit; the spec changes with the code.

## Pitfalls

- `type(v) is type(want)`, not `isinstance`: TOML `true` would pass as an
  integer otherwise.
- Every test runs with `HOME` and the XDG directories in pytest's temp dir,
  `engine.SYSROOT` in a temp dir and `SUDO_CMD=false` (`tests/conftest.py`,
  autouse). Root goes only through `run` inside `with as_root():`, which
  reads `SUDO_CMD`, so a test can never prompt for a password or change
  the machine.
- A feature mutates only through an `ensure_*` helper, a platform method or
  `run`: they respect dry run and `SYSROOT`. Commands are argv lists, never a
  shell; tests fake commands by replacing `engine._run`, not with scripts.
- Templates: a tag alone on its line vanishes with its newline
  (trim_blocks, lstrip_blocks). Booleans print as `True` in Jinja: write
  `{{ x | lower }}` where the file needs `true`.
- A `.keep` that only holds a directory in git is gated off with
  `when = "false"` in `home.toml`, so no empty file lands in `$HOME`.
