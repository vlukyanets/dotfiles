# dotfiles

A Python rework of [`vlukyanets/dotfiles`](https://github.com/vlukyanets/dotfiles)
(chezmoi + bash): the same machine description, driven by a tool of its
own with Jinja2 templates. Work in progress — today it resolves and checks
host configuration; rendering dotfiles and provisioning come next (see the
[capability map](docs/spec/CAPABILITY-MAP.md)).

## How a host is described

```
defaults.toml          every key, its type and its default; every feature off
profiles/<name>.toml   base, server, laptop
hosts/<hostname>.toml  one file per machine
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
once. Every file is checked against `defaults.toml`: an unknown key or a
value of another type fails naming the file and the key. A machine with no
file in `hosts/` gets the defaults. The rules in full:
[SPEC-config](docs/spec/SPEC-config.md).

## Commands

    uv sync
    uv run dotfiles config                            # this machine, as TOML
    uv run dotfiles config --host hyper-lin --explain # each key with the file it came from
    uv run dotfiles check                             # every host; exit 1 on any error
    uv run pytest
    uv run ruff check . && uv run ruff format --check .

A fresh machine needs git, python and uv; `uv run` installs the rest from
`uv.lock`.
