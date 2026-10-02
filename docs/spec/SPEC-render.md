# Spec: `render` — templates of the files features write

Status: approved 2026-09-23; the unconditional `home/` deploy, `render`
and `deploy` went on 2026-10-02, and `home/` came back the same day for
the dotfile templates features name. Module of the [capability map](CAPABILITY-MAP.md); depends
on `config`.

## Objective

Give every file a feature writes a Jinja2 template, so its content reads
like the file it produces and lives in the repository, not in Python
strings. Rendering only: the feature writes the text through
`files.ensure`, so the check, the dry run and root stay the engine's.

Out of scope: writing files (`engine`), deciding what to write
(`features`). Dotfiles in `$HOME` (`.gitconfig`, `environment.d`) come back
as features of their own, written the same way.

## Tech Stack

- Jinja2 ≥ 3.1, a runtime dependency installed by uv from `uv.lock` like
  `tomli-w` (no system Python packages).

## System templates: `system/`

A file a feature writes is a template at its path from `/` under
`system/`: `system/etc/makepkg.conf.d/dotfiles.conf.j2` for
`/etc/makepkg.conf.d/dotfiles.conf`. `render.template(dst, **context)`
renders it with only the context the feature passes, never the whole
config:

```python
text = template(_PACMAN_OPTIONS_CONF, pacman=pacman)
files.ensure(_PACMAN_OPTIONS_CONF, text, owner="root:root")
```

- `StrictUndefined`: a missing variable is an error, not an empty string.
- `trim_blocks` and `lstrip_blocks`: a tag alone on its line vanishes with
  its newline. Booleans print as `True`: `{{ x | lower }}` where the file
  needs `true`.
- `fail("why")` in a template stops it with that message.
- Every error is a `ConfigError` naming the template and its line,
  `system/<path>:<line>` or `home/<path>:<line>`.

## Dotfile templates: `home/`

A file a feature writes in `$HOME` is a template at its path from `~`
under `home/`: `template("~/.config/zsh/dotfiles.zsh", zsh=...)` renders
`home/.config/zsh/dotfiles.zsh.j2`. The feature writes it to
`Path.home() / ...` with `files.ensure`, as the user. Nothing reads
`home/` but the features that name a template there.

`render.source(dst)` gives a file of `system/` or `home/` as it is, no
`.j2` and no Jinja: a generated file like `home/.p10k.zsh`, whose
`${#...}` Jinja would read as its own.

## Project Structure

```
system/                templates of the files features write, at their path from /
home/                  templates of the dotfiles features write, at their path from ~
dotfiles/render.py     the Jinja2 environment and template()
tests/test_render.py   templates in tmp_path; check on a copy of the real data
```

## Testing Strategy

- A template rendered with its context, a tag alone on its line gone; `fail()`
  and an undefined variable each an error naming the template and line.
- `~/PATH` rendered from `home/PATH.j2`, its errors naming `home/`;
  `source` returns a file as it is.
- `check` on a copy of the real hosts names a value its rule refuses.

## Boundaries

- **Always:** `StrictUndefined`; a template per file a feature writes.
- **Ask first:** a third runtime dependency.
- **Never:** the whole config as a template's context.

## Decisions

1. Whitespace is handled once, by `trim_blocks` and `lstrip_blocks`, not
   with `{%-` on each tag: a template reads like the file it produces.
2. **No unconditional dotfiles** (2026-10-02). `home/` was deployed on every
   host before any feature ran, with its own manifest of modes and gates
   (`home.toml`) and its own commands (`render`, `deploy`). A dotfile is a
   feature's like any other file: the feature gates it, and the engine
   writes it. Its template is under `home/` again, but only as a template
   a feature names (`zsh`, 2026-10-02).
