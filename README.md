# dotfiles

Takes an Arch Linux, Debian or Void Linux machine from a fresh install
to a configured one. A machine is a short TOML file that inherits from
profiles; features are Python classes that check the live system and
change only what differs, writing files from Jinja2 templates. Work in
progress: today it resolves host configuration and runs `dotfiles apply`
on Arch, Debian and Void: packages from the repositories and every
feature of `dotfiles/defaults.toml`, one module each per platform in
`dotfiles/platforms/<name>/features/`. Today there are `packaging`
(pacman and makepkg drop-ins), `reflector` (the mirrorlist on a timer),
`paru` (the AUR helper), `pkgfile` (which package has a file),
`command_not_found` (its hook in zsh) and `fonts` (fonts and fontconfig)
on Arch, and on all `rustup` (cargo and rustc), `no_beep` (no PC
speaker), `git` (the user's name and email), `zsh` (zsh with
oh-my-zsh, the login shell), `locale` (locales, LANG, the console,
the timezone), `timesyncd` (the clock in sync) and `swap` (a swap file
on btrfs), the last three not on Void yet. See the
[capability map](docs/spec/CAPABILITY-MAP.md).

## How a host is described

```
dotfiles/defaults.toml  every key, its type and its default
profiles/<name>.toml    base, arch, server, laptop, vm
hosts/<hostname>.toml   one file per machine
~/.config/dotfiles/config.toml
                        this machine's resolved config, written by `dotfiles init`
```

A host or profile sets only what differs and may inherit:

```toml
extends = ["laptop"]   # profiles or other hosts, merged left to right

[features.packaging.pacman]
flags = ["Color"]
```

Tables merge; values and arrays are replaced. A shared ancestor is merged
once. Every file is checked against `dotfiles/defaults.toml`: an unknown
key or a value of another type fails naming the file and the key. The
rules in full: [SPEC-config](docs/spec/SPEC-config.md).

A machine runs from its own copy of the config: `dotfiles init [HOST]`
writes the resolved `hosts/HOST.toml` (default: this machine's hostname),
every key with its effective value, to `~/.config/dotfiles/config.toml`,
and overwrites it on the next init. `apply` and `config` read that
file; `--source PATH` reads `hosts/<hostname>.toml` of the checkout at
PATH instead, and `config --host NAME` a host of this checkout.

## Running it

A fresh machine needs git, python and uv; nothing is installed into the
system Python.

    git clone git@github.com:vlukyanets/dotfiles.git && cd dotfiles
    uv sync --locked            # creates .venv/ here, installs uv.lock into it
    uv run --isolated dotfiles check
    uv run --exact dotfiles init <host>   # ~/.config/dotfiles/config.toml

Two environments, both built by uv from `uv.lock`:

- `.venv/` runs the tool and holds its runtime dependencies only (the dev
  group is not a default one). `uv run --exact dotfiles …` syncs it first
  and removes anything else found there. After `uv sync`,
  `.venv/bin/dotfiles` works without uv too.
- Verification (tests, lint, `check`) runs with `uv run --isolated`: a
  throwaway environment per run, with the dev group added by
  `--group dev`; `.venv/` is not touched.

`uv run --locked …` refuses to start if `uv.lock` is out of date instead
of updating it.

## Commands

    uv run --exact dotfiles init [HOST]                       # hosts/HOST.toml resolved into ~/.config/dotfiles/config.toml
    uv run --exact dotfiles config                            # this machine's config, as TOML
    uv run --exact dotfiles config --source .                 # the same from hosts/<hostname>.toml of the checkout at .
    uv run --exact dotfiles config --host hyper --explain     # each key with the file it came from
    uv run --exact dotfiles apply --dry-run                   # packages and features: what would change, no sudo
    uv run --exact dotfiles apply                             # this machine; "nothing to change" when it already matches
    uv run --isolated dotfiles check                          # every host and the machine config resolve
    uv run --isolated --group dev pytest
    uv run --isolated --group dev ruff check . && uv run --isolated --group dev ruff format --check .
