# Capability Map: dotfiles (Python rework)

Approved 2026-09-23. Successor of `vlukyanets/dotfiles`
(chezmoi + bash, checked out at `../__dotfiles`): the same machine
description and the same check-before-apply contract, driven by a Python
tool instead of chezmoi. Module ids are stable; specs, plans and commits
refer to work by them.

| Module id | Responsibility | Depends on |
|---|---|---|
| `config` | Load `defaults.toml` (schema), `profiles/*.toml`, `hosts/*.toml`; resolve `extends` (host → profiles/hosts); validate every file against the schema; merge; dump the result; `check` every host | — |
| `render` | Jinja2 templates for dotfiles under `home/`, rendered with the resolved config; feature gates; deploy to `$HOME` with check-before-write (content, mode) | `config` |
| `engine` | The `lib.sh` port: `ensure_file/line/symlink/service/sysctl/...`, `as_root`, `retry`, `defer`, notices, change counting, ordered feature runner, silent clean apply | `config` |
| `packages` | `pkg.sh` port: `ensure_pkg` / `ensure_aur` / `ensure_replaced`, pacman.conf drop-ins, reflector, paru bootstrap | `engine` |
| `features` | The 38 feature scripts ported as Python modules, one per feature, grouped `system`, `shell`, `ssh`, `desktop` as today | `packages`, `render` |
| `tooling` | CI: `check` on every host, ruff, pytest; GitHub workflow | `config` |
| `docs` | README, CLAUDE.md, per-feature pages, carried over and rewritten for the tool | all |

Build order: `config` → `render`, `engine`, `tooling` → `packages` → `features` → `docs`

## Decisions carried into every module spec

1. Data model and feature set of `../__dotfiles` are the reference: every
   feature and every key there is carried over unless a spec says otherwise.
2. **Reversed from the old repo:** machine profiles now exist. A host may
   `extends` profiles (`server`, `laptop`, …) and other hosts. "Profile" is
   the name used everywhere, so "template" means only a Jinja2 template.
3. Python ≥ 3.11 (`tomllib` from the stdlib); dependencies are added only
   when a module needs them (`tomli-w` with `config`, Jinja2 with `render`).
4. Every apply reconciles live state; a clean apply prints nothing and asks
   for no password. Features are booleans; `false` never uninstalls.
5. Specs live in `docs/spec/`, one `SPEC-<id>.md` per module.
6. Commits: imperative plain-language subject, optional one-paragraph body,
   no Conventional Commits prefixes, no AI attribution. `master` starts
   empty; each module lands on its own branch.
