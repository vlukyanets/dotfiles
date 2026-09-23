# CLAUDE.md

Maintainer guide. `README.md` is the entry point for humans; `docs/spec/`
holds the capability map and the module specs that drive the work. The
chezmoi repo this replaces is checked out at `../__dotfiles` — read it for
how a feature behaves today, never edit it.

## Commands

| Task | Command |
|---|---|
| Tests | `uv run pytest` |
| Lint and format | `uv run ruff check . && uv run ruff format --check .` |
| Every host resolves | `uv run dotfiles check` |
| One host, with sources | `uv run dotfiles config --host <name> --explain` |
| A host's home tree | `uv run dotfiles render --host <name> --out <empty dir>` |
| Dotfiles into `$HOME` | `uv run dotfiles deploy --dry-run`, then without the flag |

CI (`.github/workflows/ci.yml`) runs the first three on every push to
master and every PR; uv is pinned there by version and sha256.

## Navigation

- Keys and defaults: `defaults.toml` — the schema; a new key goes here first.
  A feature is `features.<name>.enabled` plus its settings in the same table.
- Profiles `profiles/`, machines `hosts/`; one namespace for `extends`.
- Resolution, validation, merge, explain, check: `dotfiles/config.py`.
- Dotfiles: `home/` (real names, `*.j2` templates), modes and gates in
  `home.toml`, rendering in `dotfiles/render.py`.
- Registries: `data/*.toml` (ssh keys, languages), merged into the template
  context; the names a host takes from them are checked in
  `render.registries` (`REFERENCES`).
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
- Every test runs with `HOME` and the XDG directories in pytest's temp dir
  and `SUDO_CMD=false` (`tests/conftest.py`, autouse). Code that goes to
  root must read `SUDO_CMD` (default `sudo`), as `lib.sh` did, so a test
  can never prompt for a password or change the machine.
- Porting a Go template: write idiomatic Jinja2 with the same meaning, not
  chezmoi's exact output. A tag alone on its line vanishes with its newline
  (trim_blocks, lstrip_blocks). Booleans print as `True` in Jinja: write
  `{{ x | lower }}` where the file needs `true`.
- chezmoi never created an empty file; a `.keep` that only holds a directory
  in git is gated off with `when = "false"` in `home.toml`.
