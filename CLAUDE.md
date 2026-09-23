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

## Navigation

- Keys and defaults: `defaults.toml` — the schema; a new key goes here first.
- Profiles `profiles/`, machines `hosts/`; one namespace for `extends`.
- Resolution, validation, merge, explain, check: `dotfiles/config.py`.
- Why: `docs/spec/SPEC-<module>.md`, then `docs/spec/CAPABILITY-MAP.md`.

## Commits and branches

- `master` holds finished modules; each module is built on its own branch.
- Subject: one line, imperative, plain language. Body: optional, one paragraph.
- No Conventional Commits prefixes, no AI attribution lines in commits or
  pull requests.
- pytest and ruff pass before every commit; the spec changes with the code.

## Pitfalls

- `tests/test_config.py::test_hyper_lin_matches_the_chezmoi_repo` pins
  hyper-lin to the old repo's data (`tests/fixtures/old-hosts.toml`).
  Changing hyper-lin on purpose means updating that fixture in the same
  commit.
- `type(v) is type(want)`, not `isinstance`: TOML `true` would pass as an
  integer otherwise.
