# Spec: `render` — dotfiles as Jinja2 templates

Status: approved 2026-09-23. Module of the
[capability map](CAPABILITY-MAP.md); depends on `config`.

## Objective

Write the dotfiles into `$HOME`: a `home/` tree of plain files and Jinja2
templates, rendered with the resolved host config, with modes and gates in
one manifest.

Two commands:

- `dotfiles render --host X --out DIR` writes the whole home tree for any
  host into DIR. Touches nothing else. CI renders every host this way.
- `dotfiles deploy` renders for this machine and brings `$HOME` in line:
  compares, writes only what differs, prints one `->` line per change,
  prints `nothing to change` when `$HOME` already matches.

Out of scope: provisioning (features, packages, root files — `engine`,
`features`), removing files, lookup tables in `data/` (none today; one
comes back with the first template that needs it).

## Tech Stack

- Jinja2 ≥ 3.1 — second runtime dependency, installed by uv from `uv.lock`
  like `tomli-w` (no system Python packages).
- Everything else stdlib: `tomllib`, `pathlib`, `os`, `re`, `tempfile`.

## The home tree

| To get | write |
|---|---|
| a dotfile | the file at its real path: `home/.gitconfig.j2`, `home/.config/…` |
| a template | `*.j2` (Jinja2); the suffix is dropped on output |
| a private file or directory | `mode = "600"` / `"700"` in `home.toml` |
| an executable | `mode = "755"` in `home.toml` |
| a file only some hosts get | `when = "<jinja expression>"` in `home.toml` |
| a file an application also rewrites | an ordinary `.j2` that reads `current` (the file as it is in `$HOME`) |
| the home directory, the user id | `home`, `uid` |
| a template error | `{{ fail("…") }}` (a global that raises) |
| TOML in and out, deep merge, regex, a quoted string | filters `from_toml`, `to_toml`, `merge_over`, `regex_search`, `quote` (valid TOML and JSON) |

## The manifest: `home.toml`

One table per path under `home/` (file or directory, without `.j2`) that
needs a mode or a gate. Paths not listed: files 0644, directories 0755,
always deployed.

```toml
[".ssh"]
mode = "700"

```

- `when` is a Jinja2 expression over the same context as the templates;
  falsy skips the path. A gate on a directory covers everything under it.
- Every key in `home.toml` must name an existing path under `home/`, and
  only `mode` and `when` are allowed: `check` fails naming the entry.

## Template context

```
features, git                 the resolved config (config.resolve)
host                           the host name
home, uid                      target home directory and user id
current                        the target file's current text, "" if absent
```

Jinja2 environment: `StrictUndefined` (a missing key fails naming the
template and host), `keep_trailing_newline=True`, `trim_blocks=True`,
`lstrip_blocks=True`, autoescape off.

`render --out DIR` has no current `$HOME`, so `current` is `""` unless
`--current HOME` is given; `deploy` passes the real one.

## Merged files

A file an application rewrites itself stays a template that reads
`current` and merges: `{{ want | merge_over(current | from_toml) | to_toml }}`
keeps every key the application wrote, and the desired ones win. `to_toml`
is tomli-w: the first deploy rewrites the file into tomli-w's layout once;
from then on it is stable. No file under `home/` needs it at the moment.

## Deploy

For each rendered path, in order:

1. Directory missing → create with its mode. Existing directory with
   another mode, listed in `home.toml` → chmod.
2. File missing, content differs, or mode differs (`engine.differs`, the
   comparison `files.ensure` makes) → write to a temp file in the same
   directory, chmod, `os.replace`. One line:
   `-> ~/.zshrc (content differs)` / `(missing)` / `(mode 644)`.
3. Otherwise nothing.

- Never deletes. A gated-off path is left as it is.
- Never writes outside `$HOME`; a symlink on the way that leaves `$HOME`
  fails the deploy.
- `--dry-run` prints the same lines and writes nothing.
- A second run prints nothing.

## Commands

```
uv run --exact dotfiles render --host hyper --out /tmp/home-hyper
uv run --exact dotfiles render --host hyper --out DIR --current ~   # with merges from the real files
uv run --exact dotfiles deploy --dry-run
uv run --exact dotfiles deploy
uv run --isolated dotfiles check        # apply.check: also renders every host into a temp dir
```

## System templates: `system/`

A file a feature writes outside `$HOME` is a template at its path from
`/` under `system/`: `system/etc/makepkg.conf.d/dotfiles.conf.j2` for
`/etc/makepkg.conf.d/dotfiles.conf`. `render.template(dst, **context)`
renders it with the same environment and filters as `home/`, with only
the context the feature passes; an error names `system/<path>:<line>`.
The feature writes the text through `files.ensure`, so the check,
the dry run and root stay the engine's.

## Project Structure

```
home/                  the dotfiles, real names, *.j2 for templates
home.toml              modes and gates
system/                templates of the files features write outside $HOME
dotfiles/render.py     context, Jinja2 env and filters, render(), deploy()
tests/test_render.py   fixture trees in tmp_path; deploy against the tmp HOME
tests/test_home.py     the real home/ rendered for every host
```

## Code Style

```python
def render(
    host: str,
    out: Path,
    root: Path = Layout.root,
    current: Path | None = None,
    cfg: dict | None = None,
) -> list[str]:
    """Write HOST's home tree into OUT; returns the paths written, relative."""
```

Same as `config`: plain functions, `ConfigError` with file and key/line in
the message, comments on why.

## Testing Strategy

- Unit (tmp_path fixture trees): plain file copied; `.j2` rendered, suffix
  dropped; mode 600/755/700; gate on a file and on a directory, on and off;
  undefined variable → error naming template and host; `fail()`; unknown
  `home.toml` entry; filters.
- Merges: `current` reaches the templates; `merge_over` and `from_toml`
  (unknown keys kept, desired keys win); an invalid current file names the
  template.
- Deploy (tmp `HOME` from `conftest.py`): first run writes and reports,
  second run changes nothing; mode drift fixed; `--dry-run` writes nothing; symlink
  escaping `$HOME` refused.
- Real data: `check` renders hyper, echo-server and an unknown host;
  tests pin what the templates with logic (loops, gates)
  produce for the real hosts.

## Boundaries

- **Always:** `StrictUndefined`; every template change rendered for every
  host (`check`); write via temp + rename.
- **Ask first:** a third runtime dependency; deleting files on deploy;
  moving a file out of `home/` into a feature.
- **Never:** write outside `$HOME`; follow a symlink out of `$HOME`.

## Success Criteria

1. Every file under `home/` renders for every host (`check`), with the
   mode and gate `home.toml` gives it.
2. On hyper, after one `dotfiles deploy`, `deploy --dry-run` prints
   nothing.
3. `check`, pytest, ruff green locally and in CI.

## Decisions

1. A feature turned off leaves its dotfiles in place. Removing
   what was deployed can come later; it needs a record of what was written.
2. Prerequisites on a fresh machine are git, python and uv. The tool runs
   from the checkout with `uv run dotfiles …`; runtime dependencies come
   from `uv.lock`, not from system packages.
3. Modes and gates live in the `home.toml` manifest; files keep their real
   names. Chosen over encoding them in file names (two mechanisms, a name
   parser) and over one directory per feature (commits `features` to a
   layout before its spec).
4. Whitespace is handled once, by `trim_blocks` and `lstrip_blocks`, not
   with `{%-` on each tag: a template reads like the file it produces.
