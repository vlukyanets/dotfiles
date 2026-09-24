# dotfiles

Takes an Arch Linux machine from a fresh install to a configured one. A
machine is a short TOML file that inherits from profiles; dotfiles are
Jinja2 templates rendered with that configuration; features are Python
classes that check the live system and change only what differs. Work in
progress: today it resolves host configuration, renders and deploys the
dotfiles in `home/`, and runs `dotfiles apply` on Arch: pacman, makepkg
and reflector set up, packages from the repositories and the AUR, and two
features (`nobeep`, `aur`); the other features come next (see the
[capability map](docs/spec/CAPABILITY-MAP.md)).

## How a host is described

```
dotfiles/defaults.toml  every key, its type and its default; every feature off
profiles/<name>.toml    base, server, laptop
hosts/<hostname>.toml   one file per machine
```

A host or profile sets only what differs and may inherit:

```toml
extends = ["laptop"]   # profiles or other hosts, merged left to right

[features]
docker.enabled = true

[features.swap]
enabled = true
size    = "20g"
```

Tables merge; values and arrays are replaced. A shared ancestor is merged
once. Every file is checked against `dotfiles/defaults.toml`: an unknown
key or a value of another type fails naming the file and the key. A machine
with no file in `hosts/` gets the defaults. The rules in full:
[SPEC-config](docs/spec/SPEC-config.md).

## Running it

A fresh machine needs git, python and uv; nothing is installed into the
system Python.

    git clone git@github.com:vlukyanets/dotfiles.git && cd dotfiles
    uv sync --locked            # creates .venv/ here, installs uv.lock into it
    uv run dotfiles check

`uv run` always uses the project's `.venv/` (creating and syncing it first
when needed), with the system python only as the interpreter it was built
from. `uv run --locked …` refuses to start if `uv.lock` is out of date
instead of updating it. After `uv sync`, `.venv/bin/dotfiles` works without
uv too.

## Commands

    uv run dotfiles config                            # this machine, as TOML
    uv run dotfiles config --host hyper-lin --explain # each key with the file it came from
    uv run dotfiles render --host hyper-lin --out DIR # a host's home tree, into an empty DIR
    uv run dotfiles deploy --dry-run                  # what would change in $HOME
    uv run dotfiles deploy                            # write it
    uv run dotfiles apply --dry-run                   # features + dotfiles: what would change, no sudo
    uv run dotfiles apply                             # this machine, silent when it already matches
    uv run dotfiles check                             # every host resolves and renders
    uv run pytest
    uv run ruff check . && uv run ruff format --check .
