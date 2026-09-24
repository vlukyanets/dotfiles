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
  prints nothing when `$HOME` already matches.

Out of scope: provisioning (features, packages, root files — `engine`,
`features`), removing files, the registries only features read
(`firefox-privacy-config.toml`, `vscode-extensions.toml` come with their features).

## Tech Stack

- Jinja2 ≥ 3.1 — second runtime dependency, installed by uv from `uv.lock`
  like `tomli-w` (no system Python packages).
- Everything else stdlib: `tomllib`, `pathlib`, `os`, `re`, `tempfile`.

## The home tree

| To get | write |
|---|---|
| a dotfile | the file at its real path: `home/.zshrc`, `home/.config/…` |
| a template | `*.j2` (Jinja2); the suffix is dropped on output |
| a private file or directory | `mode = "600"` / `"700"` in `home.toml` |
| an executable | `mode = "755"` in `home.toml` |
| a file only some hosts get | `when = "<jinja expression>"` in `home.toml` |
| a file an application also rewrites | an ordinary `.j2` that reads `current` (the file as it is in `$HOME`) |
| a lookup table | `data/ssh-pubkeys-collection.toml`, `data/fcitx5-languages-config.toml` |
| the home directory, the user id | `home`, `uid` |
| a template error | `{{ fail("…") }}` (a global that raises) |
| TOML in and out, deep merge, regex | filters `from_toml`, `to_toml`, `merge_over`, `regex_search` |

## The manifest: `home.toml`

One table per path under `home/` (file or directory, without `.j2`) that
needs a mode or a gate. Paths not listed: files 0644, directories 0755,
always deployed.

```toml
[".zshrc"]
when = "features.zsh.enabled"

[".ssh"]
mode = "700"

[".ssh/authorized_keys"]
mode = "600"
when = "ssh.authorized_keys"

[".config/rbw"]
when = "secrets.backend == 'rbw'"

[".config/niri/lock-screen.sh"]
mode = "755"
```

- `when` is a Jinja2 expression over the same context as the templates;
  falsy skips the path. A gate on a directory covers everything under it.
- Every key in `home.toml` must name an existing path under `home/`, and
  only `mode` and `when` are allowed: `check` fails naming the entry.

## Template context

```
features, git, ssh, secrets    the resolved config (config.resolve)
host                           the host name
home, uid                      target home directory and user id
languages, ssh_keys            data/fcitx5-languages-config.toml, data/ssh-pubkeys-collection.toml
current                        the target file's current text, "" if absent
```

Jinja2 environment: `StrictUndefined` (a missing key fails naming the
template and host), `keep_trailing_newline=True`, `trim_blocks=True`,
`lstrip_blocks=True`, autoescape off.

`render --out DIR` has no current `$HOME`, so `current` is `""` unless
`--current HOME` is given; `deploy` passes the real one.

## Merged files

The two files an application rewrites itself stay templates; they read
`current` and merge:

- `.local/state/noctalia/settings.toml.j2`:
  `{{ want | merge_over(current | from_toml) | to_toml }}`. Desired keys win,
  every other key noctalia wrote passes through.
- `.config/fcitx5/profile.j2`: DefaultIM carried over from `current` when
  it is still one of the listed input methods.

`to_toml` is tomli-w: the first deploy rewrites noctalia's file into
tomli-w's layout once; from then on it is stable.

## Deploy

For each rendered path, in order:

1. Directory missing → create with its mode. Existing directory with
   another mode, listed in `home.toml` → chmod.
2. File missing, content differs, or mode differs → write to a temp file
   in the same directory, chmod, `os.replace`. One line:
   `-> ~/.zshrc (content differs)` / `(missing)` / `(mode 644)`.
3. Otherwise nothing.

- Never deletes. A gated-off path is left as it is.
- Never writes outside `$HOME`; a symlink on the way that leaves `$HOME`
  fails the deploy.
- `--dry-run` prints the same lines and writes nothing.
- A second run prints nothing.

## Commands

```
uv run --exact dotfiles render --host hyper-lin --out /tmp/home-hyper-lin
uv run --exact dotfiles render --host hyper-lin --out DIR --current ~   # with merges from the real files
uv run --exact dotfiles deploy --dry-run
uv run --exact dotfiles deploy
uv run --isolated dotfiles check        # now also renders every host into a temp dir
```

## Project Structure

```
home/                  the dotfiles, real names, *.j2 for templates
home.toml              modes and gates
data/                  ssh-pubkeys-collection.toml, fcitx5-languages-config.toml
dotfiles/render.py     context, Jinja2 env and filters, render(), deploy()
tests/test_render.py   fixture trees in tmp_path; deploy against the tmp HOME
```

## Code Style

```python
def render(host: str, out: Path, root: Path = ROOT, current: Path | None = None) -> list[Path]:
    """Write HOST's home tree into OUT; returns the paths written, relative."""
```

Same as `config`: plain functions, `ConfigError` with file and key/line in
the message, comments on why.

## Testing Strategy

- Unit (tmp_path fixture trees): plain file copied; `.j2` rendered, suffix
  dropped; mode 600/755/700; gate on a file and on a directory, on and off;
  undefined variable → error naming template and host; `fail()`; unknown
  `home.toml` entry; filters.
- Merges: noctalia with a captured settings file (unknown keys kept,
  desired keys win, missing file); fcitx5 DefaultIM kept / reset.
- Deploy (tmp `HOME` from `conftest.py`): first run writes and reports,
  second run silent; mode drift fixed; `--dry-run` writes nothing; symlink
  escaping `$HOME` refused.
- Real data: `check` renders hyper-lin, echo-server and an unknown host;
  tests pin what the templates with logic (loops, gates, registries)
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
2. On hyper-lin, after one `dotfiles deploy`, `deploy --dry-run` prints
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
