# Spec: `config` — host configuration with inheritance

Status: approved 2026-09-23. Module of the
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
- `uv` for the project and dev tools; dev dependencies `pytest`, `ruff`.

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

## Commands

```
uv sync                                           # venv + dev tools
uv run dotfiles config                            # this machine (socket.gethostname())
uv run dotfiles config --host hyper-lin           # any host, TOML on stdout
uv run dotfiles config --host hyper-lin --explain # every leaf as a dotted key, with the file it came from
uv run dotfiles check                             # every host in hosts/ + one unknown host; exit 1 on any error, all errors listed
uv run pytest
uv run ruff check . && uv run ruff format --check .
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
pyproject.toml           project, [project.scripts] dotfiles = "dotfiles.__main__:main"
dotfiles/__main__.py     argparse CLI: config, check
dotfiles/config.py       load, chain, validate, merge — pure functions over dicts and a root Path
dotfiles/defaults.toml   schema
profiles/                base, server, laptop
hosts/                   hyper-lin (extends laptop), echo-server (extends server)
tests/test_config.py     unit tests on tmp_path fixtures + checks on the real data
docs/spec/               capability map, module specs
```

Flat layout (no `src/`), so `python -m dotfiles` runs from a checkout
without installing the package.

Registries (`ssh-keys.toml`, `languages.toml`, `firefox.toml`,
`vscode.json`) are not host config; each lands in `data/` with the module
that first reads it.

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
- `uv run dotfiles check` passes on the real data.

## Boundaries

- **Always:** validate every file before merging; name file + key path in
  errors; keep `dotfiles/defaults.toml` the single schema; run pytest and
  ruff before each commit; update the spec when a decision changes.
- **Ask first:** any runtime dependency beyond `tomli-w`; changing the merge
  rule (e.g. list append).
- **Never:** push anything; write secrets; prompt
  interactively in this module.

## Success Criteria

1. `uv run dotfiles config --host hyper-lin` prints that machine's whole
   configuration as TOML: every key of the schema, with its resolved value.
2. `hosts/hyper-lin.toml` extends `laptop` and holds only what differs from
   it; `echo-server` extends `server`; `laptop` and `server` extend `base`.
3. `uv run dotfiles check` exits 0 on the repo data and 1 on each broken
   fixture from the test list, naming file and key.
4. `uv run pytest` and `ruff` pass.
5. Runs with `python -m dotfiles` from a checkout with no venv when
   `python-tomli-w` is the only third-party package installed.

## Decisions (were open questions)

1. Output is TOML (`tomli-w`), not JSON.
2. `echo-server` extends `server`, so it has every server feature.
3. `config --explain` is in this iteration.
4. Profiles: `base` = package manager, locale, zsh, CLI tools, ssh agent;
   `server` = base + sshd, tailscale; `laptop` = base + luks_discard, swap,
   snapper, zram, bluetooth, fwupd + the desktop stack. Dev toolchains and
   personal apps stay in `hyper-lin`.
5. Every feature is a table under `features` with `enabled` and its own
   settings, so a feature's switch and its settings sit in one place.
