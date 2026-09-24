# Spec: `config` — host configuration with inheritance

Status: approved 2026-09-23; machine config approved 2026-09-24. Module of the
[capability map](CAPABILITY-MAP.md).

## Objective

Describe a machine as a short host file that inherits from profiles
(`base`, `server`, `laptop`, …) or from another host, and get back one
fully resolved, validated configuration. That configuration is the only
input the later modules (`render`, `engine`, `features`) read.

This iteration only resolves and prints. Nothing is rendered, installed or
prompted for.

User stories:

- A new laptop is `hosts/<name>.toml` with `extends = ["laptop"]`, git
  identity and a handful of overrides, not 70 feature flags copied by hand.
- A second machine like an existing one is `extends = ["hyper-lin"]` plus
  what differs.
- A typo (`features.nvidai`), a wrong type (`features.swap.size = 20`), an unknown
  parent or an inheritance cycle fails with the file and the key path
  named, for every host at once in CI.

## Tech Stack

- Python ≥ 3.11: `tomllib`, `argparse`, `socket` from the stdlib.
- `tomli-w` for TOML output — the one runtime dependency (Arch: `python-tomli-w`, extra).
- `uv` for the project and dev tools; dev dependencies `pytest`, `ruff`, in a
  group that is not a default one: `.venv/` holds the runtime only, and
  verification brings the group into a throwaway environment
  (`uv run --isolated --group dev`).

## Data model

```
dotfiles/defaults.toml  schema: every key, its type, its default
profiles/<name>.toml    partial config + optional extends
hosts/<hostname>.toml   partial config + optional extends
```

A profile or host file:

```toml
extends = ["laptop"]           # optional; names of profiles or hosts, merged left to right

[git]
name  = "Valentin Lukyanets"
email = "valikluks95@gmail.com"

[features]
docker.enabled = true          # a feature with no settings: one dotted key

[features.swap]                # a feature with settings: its own table
enabled = true
size    = "20g"
```

Every feature is a table `features.<name>` with `enabled` (default
`false`) and its settings; `git`, `secrets` and `ssh` are not features and
stay at the top level. `features.locale.console` holds the console font,
which the `locale` feature applies.

Resolution for host `H`:

1. **Chain.** Depth-first walk of `extends`, post-order, each file visited
   once: `extends = ["a", "b"]` where both extend `base` yields
   `defaults → base → a → b → H`. A shared ancestor is merged once, at its
   first position, so `b` does not reset what `a` set.
2. **Names.** A name in `extends` is looked up in `hosts/` and `profiles/`;
   a name present in both is an error. Unknown name → error.
   A cycle → error listing the cycle (`a → b → a`).
3. **Validation, per file, before merging.** Every key must exist in
   `dotfiles/defaults.toml` at the same path, at any depth, with the same
   type. `bool` and `int` are different types; lists match any list;
   tables recurse. `extends` is the only key not in the schema and must be a list
   of strings. Errors name the file and the dotted key path:
   `hosts/hyper-lin.toml: features.nvidai: unknown key`.
4. **Merge.** Tables merge recursively; scalars and lists are replaced by
   the later file, so lists never append.
5. **Value checks:** `secrets.backend` ∈ {`none`, `rbw`},
   checked on the merged result.
6. **Unknown host** (no `hosts/<name>.toml`): the defaults alone. Not an
   error.

The resolved config does not contain `extends`.

## Machine config

A machine runs from its own copy of the resolved config, not from the
repository's `hosts/`:

- **Where:** `$XDG_CONFIG_HOME/dotfiles/config.toml`
  (`~/.config/dotfiles/config.toml`).
- **What:** effective values only. It is the full resolved config of one
  host (every key of the schema, inherited and computed values included),
  the same TOML `dotfiles config --host NAME` prints. There is no `extends`
  in it, and no scripts, templates or registries: those stay in the checkout.
- **Written by `dotfiles init [NAME]`**, which creates or overwrites the file
  with the resolved config of host NAME (default: this machine's
  hostname) from `hosts/` of the checkout, or of `--source PATH`. It prints
  `-> ~/.config/dotfiles/config.toml (missing | content differs)`, or
  `nothing to change` when the file already holds exactly that. A header
  comment names the host and the checkout it came from.
- **Read by `apply`, `deploy`, `config` and `render`.** The file is
  validated against the schema like any host file (an unknown key or a
  wrong type fails with the file and key named) and merged over
  `defaults.toml`, so a key added to the schema later gets its default until
  the next `init`.
- **Missing file:** `error: no ~/.config/dotfiles/config.toml — run dotfiles
  init <host>, or pass --source <checkout>`, exit 1. Nothing falls back to
  defaults.
- **`--source PATH`** (on `apply`, `deploy`, `config`, `render`, `init`,
  `check`) reads the config from the checkout at PATH instead of
  `~/.config/dotfiles`: `hosts/<name>.toml` there with everything it
  extends, as before. The name is `--host` where the command has it,
  else the hostname. `--host NAME` without `--source` means `--source`
  of the checkout the tool runs from. Templates, `home.toml` and `data/`
  always come from the checkout the tool runs from.
- **`check`** resolves and renders every host in `hosts/` as before, plus
  `~/.config/dotfiles/config.toml` when it exists (listed as `local`).
- `hosts/` stays in the repository: it is what `init` reads, and CI checks it.

## Commands

```
uv sync                                           # .venv/: runtime dependencies only
uv run --exact dotfiles init                      # ~/.config/dotfiles/config.toml from hosts/<hostname>.toml
uv run --exact dotfiles init vm-box               # ... from hosts/vm-box.toml; overwrites the file
uv run --exact dotfiles config                    # this machine, from ~/.config/dotfiles/config.toml
uv run --exact dotfiles config --source .         # this machine, from hosts/<hostname>.toml of the checkout at .
uv run --exact dotfiles config --host hyper-lin   # any host of this checkout, TOML on stdout
uv run --exact dotfiles config --host hyper-lin --explain # every leaf as a dotted key, with the file it came from
uv run --isolated dotfiles check                  # every host in hosts/ + one unknown host (+ local); exit 1 on any error, all errors listed
uv run --isolated --group dev pytest              # verification: a throwaway environment, .venv/ untouched
uv run --isolated --group dev ruff check . && uv run --isolated --group dev ruff format --check .
python -m dotfiles config                         # same, without uv (bootstrap path)
```

Output of `config` is TOML, the same shape as the input files. `--explain`
prints one line per leaf, itself valid TOML:

```
features.docker.enabled = true  # hosts/hyper-lin.toml
features.sshd.enabled = true  # profiles/server.toml
features.swap.size = ""  # dotfiles/defaults.toml
```

Errors go to stderr as `error: <file>: <key>: <reason>`, exit 1.

## Project Structure

```
pyproject.toml           project, [project.scripts] dotfiles = "dotfiles.cli:main"
dotfiles/cli.py          argparse CLI: init, config, render, deploy, check, apply
dotfiles/__main__.py     `python -m dotfiles`: calls cli.main
dotfiles/config.py       load, chain, validate, merge — pure functions over dicts and a root Path
dotfiles/defaults.toml   schema
profiles/                base, server, laptop, vm
hosts/                   hyper-lin (extends laptop), echo-server (extends server)
tests/test_config.py     unit tests on tmp_path fixtures + checks on the real data
docs/spec/               capability map, module specs
```

Flat layout (no `src/`), so `python -m dotfiles` runs from a checkout
without installing the package.

Registries (`ssh-pubkeys-collection.toml`, `fcitx5-languages-config.toml`,
`firefox-privacy-config.toml`, `vscode-extensions.toml`) are not host config;
each lands in `data/` with the module that first reads it.

## Code Style

```python
def resolve(root: Path, host: str) -> dict:
    """Merged config for HOST: defaults, then every file in its chain."""
    schema = load(root / DEFAULTS)
    config = copy.deepcopy(schema)
    for name, path in chain(root, host):
        data = load(path)
        validate(data, schema, where=path.relative_to(root))
        merge(config, data)
    config.pop("extends", None)
    return config
```

- Pure functions over plain `dict`s; no classes until something needs state.
- Errors are `ConfigError(message)` raised at the first problem inside a
  file; `check` collects them across hosts.
- Type hints on public functions; ruff defaults, line length 100.
- Comments say why, not what.

## Testing Strategy

- `pytest`, one file `tests/test_config.py`, fixtures written to `tmp_path`.
- Cases: single-level extends; multi-parent order; diamond (shared ancestor
  merged once); host extends host; cycle; unknown parent; name in both
  directories; unknown key at depth 1 and 2; wrong type incl. `bool` vs
  `int`; `extends` of wrong type; list replaced not appended; unknown host
  = defaults; `secrets.backend` enum.
- `--explain` names the right file for a value set in defaults, a profile
  and the host.
- `uv run --isolated dotfiles check` passes on the real data.

## Boundaries

- **Always:** validate every file before merging; name file + key path in
  errors; keep `dotfiles/defaults.toml` the single schema; run pytest and
  ruff before each commit; update the spec when a decision changes.
- **Ask first:** any runtime dependency beyond `tomli-w`; changing the merge
  rule (e.g. list append).
- **Never:** push anything; write secrets; prompt
  interactively in this module.

## Success Criteria

1. `uv run --exact dotfiles config --host hyper-lin` prints that machine's whole
   configuration as TOML: every key of the schema, with its resolved value.
2. `hosts/hyper-lin.toml` extends `laptop` and holds only what differs from
   it; `echo-server` extends `server`; `laptop` and `server` extend `base`.
3. `uv run --isolated dotfiles check` exits 0 on the repo data and 1 on each broken
   fixture from the test list, naming file and key.
4. `uv run --isolated --group dev pytest` and `ruff` pass.
5. Runs with `python -m dotfiles` from a checkout with no venv when
   `python-tomli-w` is the only third-party package installed.

## Decisions (were open questions)

1. Output is TOML (`tomli-w`), not JSON.
2. `echo-server` extends `server`, so it has every server feature.
3. `config --explain` is in this iteration.
4. Profiles: `base` = package manager, locale, zsh, CLI tools, ssh agent;
   `server` = base + sshd, tailscale; `laptop` = base + luks_discard, swap,
   snapper, zram, bluetooth, fwupd + the desktop stack; `vm` = laptop
   without luks_discard, bluetooth, fwupd and swap. Dev toolchains and
   personal apps stay in `hyper-lin`.
5. Every feature is a table under `features` with `enabled` and its own
   settings, so a feature's switch and its settings sit in one place.
6. **The machine keeps its own resolved config** in
   `~/.config/dotfiles/config.toml`, written by `init`: a later change in
   `hosts/` or `profiles/` reaches the machine only through the next `init`,
   and what the machine runs with is one file to read. `--source PATH` reads
   a checkout instead.
