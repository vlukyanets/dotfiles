# Capability Map: dotfiles

Approved 2026-09-23. A Python tool that describes each machine in TOML
and brings the live system in line with that description, checking
before every change. Module ids are stable; specs, plans and commits
refer to work by them.

| Module id | Responsibility | Depends on |
|---|---|---|
| `config` | Load `dotfiles/defaults.toml` (schema), `profiles/*.toml`, `hosts/**/*.toml`; resolve `extends` (host → profiles/hosts); validate every file against the schema; merge; dump the result; `check` every host | — |
| `render` | Jinja2 templates under `system/` and `home/` for the files features write, rendered with the context a feature passes | `config` |
| `engine` | `files.ensure/line/symlink`, `ensure_service/sysctl/...`, `shell.as_root`, `retry`, `defer`, notices, ordered feature runner, a clean apply that only says `nothing to change` | `config` |
| `packages` | Install from the repositories, removing what a feature replaces | `engine` |
| `features` | One Python module per feature and platform (`platforms/<name>/features/`, Linux's the fallback) for each in `dotfiles/defaults.toml` | `packages`, `render` |
| `tooling` | CI: `check` on every host, ruff, pytest; GitHub workflow | `config` |
| `docs` | README, CLAUDE.md, a page per feature | all |

Build order: `config` → `render`, `engine`, `tooling` → `packages` → `features` → `docs`

## Decisions carried into every module spec

1. `dotfiles/defaults.toml` lists every feature and every key; a module
   that adds a feature or a setting adds it there first.
2. A host may `extends` profiles (`server`, `laptop`, …) and other hosts.
   "Profile" is the name used everywhere, so "template" means only a
   Jinja2 template.
3. Python ≥ 3.11 (`tomllib` from the stdlib); dependencies are added only
   when a module needs them (`tomli-w` with `config`, Jinja2 with `render`).
   A fresh machine needs git, python and uv, nothing else: the tool runs
   from the checkout with `uv run dotfiles …`, dependencies from `uv.lock`.
4. Every apply reconciles live state; a clean apply prints only `nothing to
   change` and asks for no password. A feature is `features.<name>` with `enabled` and its
   settings, or without `enabled` if it always runs (`packaging`);
   `enabled = false` never uninstalls.
5. Specs live in `docs/spec/`, one `SPEC-<id>.md` per module.
6. Commits: imperative plain-language subject, optional one-paragraph body,
   no Conventional Commits prefixes, no AI attribution. Each module lands
   on its own branch.
