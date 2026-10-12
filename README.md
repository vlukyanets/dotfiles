# dotfiles

The configuration of my machines, kept as plain copies of their files.

- `nodes/<node>/` holds one machine's files at their paths from `/`:
  `nodes/hyper/etc/ssh/sshd_config.d/10-local.conf`.
- `nodes/<node>/.meta` lists only the files and directories whose owner or
  mode differ from the defaults, one per line:
  `0600 root:root etc/ssh/ssh_host_ed25519_key`. A directory's path ends in
  a slash: `0700 valentinl:valentinl home/valentinl/`. The defaults are
  `<user>:<user>` for `home/<user>/` and below, `root:root` elsewhere; 0644
  for a file, or 0755 if executable; 0755 for a directory.
- `dotfiles/` is the Python package behind the `dotfiles` command;
  `uv run python -m dotfiles` runs it too.
- `tests/` holds its tests.

Why it is built this way: [docs/decisions.md](docs/decisions.md).

## Setting up

```sh
sudo pacman -S python uv
uv sync
git config core.hooksPath .githooks
```

The last line turns on the pre-commit hook in `.githooks/`. Cloning does
not turn it on; that is up to you. Without it, nothing stops a secret
before it is pushed.

## Checking for secrets

```sh
uv run dotfiles scan --staged          # the lines the staged changes add
uv run dotfiles scan --history         # the lines every commit adds
uv run dotfiles scan nodes/hyper       # whole files, or a directory
```

The rules are in `secret_leaks.toml`: hundreds of known token formats,
plus rules for what dotfiles hold, like Wi-Fi passwords in `psk=` lines.
The scanner weighs keywords, entropy and allowlists, so placeholders like
`${WIFI_PASSWORD}` or `{{ .psk }}` pass, and it decodes base64, hex,
percent and unicode-escaped text to find secrets hidden in it. It names
the file, the line and the rule, never the value, and exits with 1 if it
finds something. A line that only looks like a secret can be marked with
`secret-leaks:allow`. `dotfiles add` runs the same check on each file it
copies.

The pre-commit hook runs `dotfiles scan --staged`; CI runs
`dotfiles scan --history` on every pull request.

## Adding a file

```sh
uv run dotfiles add hyper /etc/ssh/sshd_config.d/10-local.conf ~/.config/niri/config.kdl
```

The command copies each file into `nodes/hyper/` at its path and updates
`nodes/hyper/.meta` when the owner or mode of the file, or of any directory
above it, is not the default. Running it again updates the copies that
changed and prints `unchanged` for the rest.

This repository is public, so the command refuses a file that looks like it
holds a secret: a known token format (GitHub, AWS, Slack, API keys), a
private key, or a line like `psk=…` or `password: …`. It names the file,
the line and the kind of secret, never the value. Keep such a file as a
template instead: `--template`, below. It also warns about a file that others cannot read, since
it may hold a secret too. A file or directory closed to you is read
through one `sudo` helper, started at the first need, so the password is
asked once.

- `--dry-run` prints what would change and changes nothing.
- `--force` copies a file even if it looks like it holds a secret.
- `--template` keeps each file as a template; see [Templates](#templates).
- `--root DIR` reads the files from `DIR` instead of `/`.

Only regular files are supported; a directory or a symlink is an error.

## Installing a node

```sh
uv run dotfiles install --dry-run hyper
uv run dotfiles install hyper
```

The command puts each file of `nodes/hyper/` at its path from `/`, with the
owner and mode from `.meta` or the defaults. It prints each change and
changes nothing else. Run twice, the second run prints nothing.

| On the machine | What happens | Printed |
|---|---|---|
| Missing file | Written | `installed /etc/x` |
| Other contents | The old file is kept as a backup, then replaced | `updated /etc/x (backup …/.backups/hyper/20261011-213000/etc/x)` |
| Same contents, other owner or mode | Owner and mode set; no backup | `owner /etc/x root:root → alice:alice`, `mode /etc/x 0644 → 0600` |
| Same | Nothing | Nothing |
| Missing directory | Created | `created /etc/x/` |
| Directory with a `.meta` line | Owner and mode set to that line | `mode /home/alice/.ssh/ 0755 → 0700` |
| Directory without one | Left alone | Nothing |

- A file is written to a temporary file beside it and renamed over the
  target, so it is never missing or half-written.
- The backup is a copy of the old file, made before it is replaced, in
  `.backups/<node>/<YYYYmmdd-HHMMSS>/` of this repository, at the file's
  path from `/`. The time is when the run started, in local time, so one
  run keeps all its backups in one directory. A copy is yours and 0600;
  the old file's owner and mode are in that directory's `.meta`, a line
  for each file, in the format of a node's. `.backups/` is closed to others (0700) and ignored by
  git; `dotfiles cleanup` removes what you no longer need.
- The command runs as you. What you cannot write goes through one
  `sudo` helper, started at the first need, so the password is asked once.
- The whole plan is built before the first write. The command stops with an
  error, having changed nothing, when a user or group does not exist on the
  machine, when a target or a directory on the way is a symlink, when a file
  is not a regular file or a directory is not a directory, when a `.meta`
  line names a path the node does not have, or when the node or the root
  does not exist.
- `--dry-run` prints the same lines and changes nothing. It may still read
  through `sudo`.
- `--root DIR` installs under `DIR` instead of `/`.

It does not remove what the node lacks, show diffs, or install packages and
services.

## Templates

A file that holds a secret, or a value only the machine knows, is kept as a
template: `nodes/<node>/<path>.tmpl`, with a placeholder in place of each
value.

```
# nodes/hyper/etc/NetworkManager/system-connections/home.nmconnection.tmpl
[wifi-security]
psk={{ wifi_home_psk }}
```

- `install` writes it to its path without `.tmpl`, each `{{ name }}`
  filled in; `name` is `[a-z0-9_]`, and anything else is left as it is.
  Its `.meta` line names the template: `0600 root:root
  etc/NetworkManager/system-connections/home.nmconnection.tmpl`.
- The values are in `~/.config/dotfiles/<node>.toml` (under
  `$XDG_CONFIG_HOME` when it is set), outside the repository, a flat TOML
  table of strings, 0600 in a 0700 directory:
  `wifi_home_psk = "…"`. A value can be written there by hand, a
  multi-line one as `"""…"""`.
- A value `install` does not find, it asks for without echo, before the
  first write, and adds to that file. Without a terminal it stops with an
  error instead. `--dry-run` asks nothing and prints
  `unfilled /etc/x (wifi_home_psk)`.
- `status` fills a template with the values it has and compares the result;
  one it cannot fill is `unfilled`. `-v` diffs the template as it is
  against the machine's file with each of its values put back as its
  placeholder (`+++ /etc/x (values hidden)`), so the values it knows are
  not shown. A value changed on the machine is not one it knows, and shows.
- A value is never printed. A template is checked for secrets like any
  other file, so one left in it is still caught.
- A node cannot keep both `x` and `x.tmpl`, and `add` refuses a file kept
  as a template, or one whose name ends in `.tmpl`.

```sh
uv run dotfiles add --template hyper /etc/NetworkManager/system-connections/home.nmconnection
```

`add --template` makes the template from the machine's file:

- Each secret the rules find is named by you, asked in the terminal with
  its place but never its value:
  `/etc/x:12: wifi-psk, name for it:`. The secret goes into the values
  file and `{{ name }}` into the template, everywhere the secret is in
  the file.
- A secret the values file already has keeps its name, unasked, so a
  password in two files has one name, and running it again changes
  nothing.
- The template is checked for secrets again; if any is left, nothing is
  written. So is a secret found but not in its line as it is (decoded
  from base64, say): make that template by hand.
- A file with no secret is copied as it is, to put placeholders in by hand.
- `--dry-run` asks nothing: `added nodes/hyper/etc/x.tmpl (2 values to name)`.
- A file kept as a plain copy is not turned into a template; `git rm` it
  first.

## Checking what drifted

```sh
uv run dotfiles status hyper           # what differs, like git status
uv run dotfiles status -v hyper        # and a diff of each modified file
```

The node plays git's index and the machine its working tree; each arrow
goes from the node to the machine. The command writes nothing, and exits
with 0 whether or not something differs.

```
Node hyper, root /

Changes on the machine:
  (dotfiles add hyper <path> keeps them; dotfiles install hyper undoes them)
        modified:  /etc/pacman.conf
        mode:      /etc/ssh/sshd_config.d/10-local.conf  0600 → 0644
        owner:     /etc/x  root:root → alice:alice
        missing:   /etc/y

Directories off their defaults, with no .meta line:
  (dotfiles add records them with the next file added under them)
        mode:      /home/alice/.ssh/  0755 → 0700
```

- It reads what `install` reads, through `sudo` when needed, and stops on
  the same errors.
- A missing directory shows as its missing files.
- The second list is what `install` leaves alone: a directory without a
  `.meta` line whose owner or mode is not the default.
- `-v` prints the machine's files, secrets and all, except the known
  values of a template; a binary file is only named. An agent runs it on a
  real machine only when the owner asks.
- `--root DIR` compares `DIR` instead of `/`.

## Removing backups

```sh
uv run dotfiles cleanup --dry-run      # what it would remove
uv run dotfiles cleanup                # every backup
uv run dotfiles cleanup --keep 3       # all but the last 3 runs of each node
uv run dotfiles cleanup --older-than 30   # the runs older than 30 days
```

It removes whole runs, the directories under `.backups/<node>/`, and
prints each one. It stops with an error, having removed nothing, when a
directory there is not named like a run.

## Testing

```sh
uv run pytest
uv run ruff check                      # lint, with ruff's default rules
uv run mypy                            # types, of dotfiles/ and tests/
```

The tests run on a fake filesystem (pyfakefs) with fake owners; they never
touch the machine. CI runs all three on every pull request, on Python 3.12,
the oldest `pyproject.toml` allows.

## License

Released into the public domain; see [LICENSE](LICENSE). `secret_leaks.toml`
contains third-party rules under the MIT license; see the notice at its top.
