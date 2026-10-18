# dotfiles

The configuration of my machines, kept as plain copies of their files.

- `hosts/<host>/` holds one machine's files at their paths from `/`:
  `hosts/hyper/etc/ssh/sshd_config.d/10-local.conf`.
- `hosts/<host>/.meta` lists only the files and directories whose owner or
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

The command runs on Arch, Debian and the distributions like them, by `ID`
and `ID_LIKE` in `/etc/os-release`; `add`, `install`, `restore` and
`status`, which read or write the machine, refuse another. It works on a
clone of this repository. There are two ways to have one.

**Installed, like chezmoi.** uv installs the command from GitHub, and
`init` clones the repository into `~/.local/share/dotfiles` (under
`$XDG_DATA_HOME` when it is set, or into `$DOTFILES_REPO`):

```sh
sudo pacman -S git uv
uv tool install git+https://github.com/vlukyanets/dotfiles
dotfiles init
dotfiles install --dry-run
```

- `uv tool upgrade dotfiles` updates the command;
  `git -C ~/.local/share/dotfiles pull` updates the hosts.
- `add` writes into the clone; commit and push from there.
- `dotfiles init --slim` leaves the old versions of files on GitHub;
  git fetches one when a command needs it (`git log -p`, `git blame`), and
  commit, push and pull work as usual.

**In a clone of your own**, to work on the command itself:

```sh
sudo pacman -S git uv
git clone https://github.com/vlukyanets/dotfiles && cd dotfiles
uv sync
git config core.hooksPath .githooks
```

Here `uv run dotfiles …` works on this clone, whatever `$DOTFILES_REPO`
says. The last line turns on the pre-commit hook in `.githooks/`, in
either clone: it stops a commit that holds a secret or leaves a broken
host. Cloning does not turn it on; that is up to you. Without it, nothing
stops a secret before it is pushed.

## Checking for secrets

```sh
uv run dotfiles scan --staged          # the lines the staged changes add
uv run dotfiles scan --history         # the lines every commit adds
uv run dotfiles scan hosts/hyper       # whole files, or a directory
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

## Checking the hosts

```sh
uv run dotfiles check          # every host in hosts/
uv run dotfiles check hyper    # the hosts named
```

```
hyper: ok
laptop:
  …/hosts/laptop/.meta:3: not `<mode> <owner>:<group> <path>`
  …/hosts/laptop/.meta: the host has no etc/nope
  …/hosts/laptop/.hooks:2: not `<pattern> <command>`
```

The command finds in each host what would stop `install` without a
machine: what does not parse in `.meta`, `.hooks` and `.packages`, a
`.meta` line for a path the host does not have, a symlink or a path under
a symlinked directory of the host, a file kept beside its template, a
symlink named like a template, a template that is not UTF-8, and a host
name `install` refuses. It prints each host in name order, `ok` or its
problems, and exits with 1 if a host has one. It reads only the
repository, so it runs anywhere, as any user; whether a user, a group or
a package exists is for `install` to find on the machine. Why:
[decision 33](docs/decisions.md).

The pre-commit hook runs it after `dotfiles scan --staged`, on the hosts
as they are in the working tree; CI runs it on every pull request and on
`master`.

## Making a host

```sh
uv run dotfiles new                # hosts/<hostname>/
uv run dotfiles new --host hyper   # hosts/hyper/
```

The command makes the host's directory with an empty `.meta`, which keeps
the directory in git and lists no exceptions. It leaves a host that exists
as it is. Why: [decision 36](docs/decisions.md).

Every command that works on one host takes the machine's hostname for it,
here `hyper`, as it is; `--host <host>` names another. A host's name is a
hostname: labels of letters, digits and hyphens joined by dots, such as
`Hyper.local`; why: [decision 35](docs/decisions.md). A new host is made
only when named: by `new`, or by `add` with `--host`; with the hostname
alone, `add` refuses a host that `hosts/` does not have. Why:
[decision 10](docs/decisions.md).

## Adding a file

```sh
uv run dotfiles add /etc/ssh/sshd_config.d/10-local.conf ~/.config/niri/config.kdl
```

The command copies each file into `hosts/hyper/` at its path and updates
`hosts/hyper/.meta` when the owner or mode of the file, or of any directory
above it, is not the default. Running it again updates the copies that
changed and prints `unchanged` for the rest.

This repository is public, so the command refuses a file that looks like it
holds a secret: a known token format (GitHub, AWS, Slack, API keys), a
private key, or a line like `psk=…` or `password: …`. It names the file,
the line and the kind of secret, never the value. Keep such a file as a
template instead: `--template`, below. It also warns about a file that
others cannot read, since it may hold a secret too. A file or directory
closed to you is read through one `sudo` helper, started at the first need,
so the password is asked once.

- `--dry-run` prints what would change and changes nothing.
- `--force` copies a file even if it looks like it holds a secret.
- `--template` keeps each file as a template; see [Templates](#templates).
- `--root DIR` reads the files from `DIR` instead of `/`.

A symlink is kept as a symlink, its target as it is, whatever it points
to: `added hosts/hyper/etc/localtime -> /usr/share/zoneinfo/UTC`. It gets
no `.meta` line and is not checked for secrets, since its target is a path;
it cannot be a template. A directory, a path through a symlinked
directory on the machine or in the host, or a path the host keeps as a
directory is an error; so is forgetting a path through a symlinked
directory in the host.

### Taking back what changed

```sh
uv run dotfiles add  # each file of the host changed on the machine
```

With no path and no `--package`, the command adds each file and symlink of
the host that `status` lists as changed on the machine: `modified`,
`target:`, `mode:` or `owner:`. It skips, with a line for each, a file
missing on the machine, which `forget` drops, and a template, which
`add --template` with its path remakes. Why:
[decision 31](docs/decisions.md). `--dry-run`, `--force` and `--root` work
as above; `--template` needs its paths.

## Forgetting a file

```sh
uv run dotfiles forget /etc/ssh/sshd_config.d/10-local.conf
```

The command removes the file's copy, its template or its symlink from
`hosts/hyper/` with its line in `.meta`, and so does it for each directory
of the host left with no files. The machine keeps the file. `--dry-run`
prints what would change and changes nothing.

## Packages

`hosts/<host>/.packages` lists the packages of the host, a name per line.
A host is one machine, so the names are those of its distribution:

| Distribution, by `ID` or `ID_LIKE` in `/etc/os-release` | Installed | Installed on purpose | Installed with |
|---|---|---|---|
| `arch` | `pacman -Qq` | `pacman -Qqe` | `paru -S --needed`, as you; without paru, `sudo pacman -S --needed` |
| `debian` (Ubuntu too) | `dpkg-query -W`, status `ii` | `apt-mark showmanual` | `sudo apt-get install` |

```sh
uv run dotfiles add --package niri paru       # must be installed
uv run dotfiles forget --package niri         # the machine keeps it
uv run dotfiles add /etc/hosts --package vim  # paths first
```

- `install` installs the packages the machine lacks first, in one command,
  printing `installed packages niri waybar`, since a package may bring a
  user or a directory the files need. With `--dry-run` it only prints;
  with `--root` other than `/` it prints `skipped packages`.
- A package installed on purpose that the list lacks is left alone;
  `status` lists it, if the host has a list. Removing it is yours. On
  Debian, what the installer chose counts as on purpose too.
- paru and apt ask before they install; nothing answers for you.
- An AUR package needs paru; without it, pacman fails on it.

## Installing a host

```sh
uv run dotfiles install --dry-run
uv run dotfiles install
```

The command puts each file of `hosts/hyper/` at its path from `/`, with the
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
| Missing symlink | Made | `installed /etc/localtime -> /usr/share/zoneinfo/UTC` |
| Symlink to the same target | Nothing | Nothing |
| Symlink to another target, or a file where the host has a symlink, or the other way round | The old one is kept as a backup, then replaced | `updated /etc/localtime -> /usr/share/zoneinfo/UTC (backup …)` |

- A file is written to a temporary file beside it and renamed over the
  target, so it is never missing or half-written. So is a symlink.
- A symlink in the host is put as it is, its target not rewritten and not
  needed to exist. Its owner is the default, set when it is made and never
  compared; it has no mode and no `.meta` line. Why:
  [decision 30](docs/decisions.md).
- The backup is a copy of the old file, made before it is replaced, in
  `.backups/<host>/<YYYYmmdd-HHMMSS>/` of this repository, at the file's
  path from `/`. The time is when the run started, in local time, so one
  run keeps all its backups in one directory. A copy is yours and 0600;
  the old file's owner and mode are in that directory's `.meta`, a line
  for each file, in the format of a host's. A symlink is kept as a
  symlink, with no line. `.backups/` is closed to others (0700) and ignored by
  git; `dotfiles restore` puts it back, and `dotfiles cleanup` removes what
  you no longer need.
- The command runs as you. What you cannot write goes through one
  `sudo` helper, started at the first need, so the password is asked once.
- The host is read first, before the packages, and the command stops with
  an error, having changed nothing, listing every problem of the host at
  once: a `.meta`, `.hooks` or `.packages` file that is not UTF-8, or a
  line of it that does not parse; a `.meta` line for a path the host does
  not have, a symlink or a path under a symlinked directory of the host; a
  file kept beside its template; a symlink named like a template; a
  template that is not UTF-8. `status` lists them the same way, and `add`
  and `forget` every `.meta` line that does not parse. Why:
  [decision 32](docs/decisions.md).
- Then the whole plan is built before the first write. The command stops
  with an error, having changed nothing, at the first problem of the
  machine: a user or group that does not exist, a directory on the way
  that is a symlink, a target that is not a regular file or a symlink or a
  directory that is not a directory; or when the host or the root does not
  exist.
- `--dry-run` prints the same lines and changes nothing. It may still read
  through `sudo`.
- `--root DIR` installs under `DIR` instead of `/`.

It does not remove what the host lacks, show diffs, or enable services.

### Running commands after a file changes

`hosts/<host>/.hooks` names a command to run when `install` writes a file,
one line each: a pattern of paths from `/`, then the command.

```
# hosts/hyper/.hooks
etc/ssh/sshd_config.d/*          sudo systemctl reload sshd
etc/systemd/system/*             sudo systemctl daemon-reload
home/valentinl/.config/waybar/*  systemctl --user restart waybar
```

- After the last write, each command whose pattern matches a file
  installed or updated runs once, in the order of the file, printing
  `ran <command>`. A change of owner or mode alone runs nothing. A symlink
  made counts as written; one in `*.wants/` starts nothing by itself, since
  systemd reads it on `daemon-reload`, which `etc/systemd/system/*` above
  runs, or at boot.
- A template matches by its path without `.tmpl`. The pattern is
  [fnmatch](https://docs.python.org/3/library/fnmatch.html)'s, so `*`
  matches a slash too; empty lines and lines starting with `#` are skipped.
- A command runs as you, by the shell; write `sudo` where it needs root.
  One that fails stops the command with an error, the files already written.
- `--dry-run` prints the commands and runs none; with `--root` other than
  `/`, they are printed as `skipped`, since that is not the running system.

## Templates

A file that holds a secret, or a value only the machine knows, is kept as a
template: `hosts/<host>/<path>.tmpl`, with a placeholder in place of each
value.

```
# hosts/hyper/etc/NetworkManager/system-connections/home.nmconnection.tmpl
[wifi-security]
psk={{ wifi_home_psk }}
```

- `install` writes it to its path without `.tmpl`, each `{{ name }}`
  filled in; `name` is `[a-z0-9_]`, and anything else is left as it is.
  Its `.meta` line names the template: `0600 root:root
  etc/NetworkManager/system-connections/home.nmconnection.tmpl`.
- The values are in `~/.config/dotfiles/<host>.toml` (under
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
- A host cannot keep both `x` and `x.tmpl`, and `add` refuses a file kept
  as a template, or one whose name ends in `.tmpl`.

```sh
uv run dotfiles add --template /etc/NetworkManager/system-connections/home.nmconnection
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
- `--dry-run` asks nothing: `added hosts/hyper/etc/x.tmpl (2 values to name)`.
- A file kept as a plain copy is not turned into a template; `git rm` it
  first.

## Checking what drifted

```sh
uv run dotfiles status     # what differs, like git status
uv run dotfiles status -v  # and a diff of each modified file
```

The host plays git's index and the machine its working tree; each arrow
goes from the host to the machine. The command writes nothing, and exits
with 0 whether or not something differs.

```
Host hyper, root /

Changes on the machine:
  (dotfiles add --host hyper <path> keeps them; dotfiles install --host hyper undoes them)
        modified:  /etc/pacman.conf
        mode:      /etc/ssh/sshd_config.d/10-local.conf  0600 → 0644
        owner:     /etc/x  root:root → alice:alice
        missing:   /etc/y
        target:    /etc/localtime  /usr/share/zoneinfo/UTC → /usr/share/zoneinfo/Europe/Berlin

Directories off their defaults, with no .meta line:
  (dotfiles add records them with the next file added under them)
        mode:      /home/alice/.ssh/  0755 → 0700
```

- It reads what `install` reads, through `sudo` when needed, and stops on
  the same errors.
- A missing directory shows as its missing files.
- The packages of the host the machine lacks are listed after the changes,
  as `package:   niri`, then the packages installed on purpose that the
  host's list lacks, if it has one; neither with `--root`.
- `target:` is a symlink pointing elsewhere, or a symlink on one side and a
  file, shown as `(a file)`, on the other. A symlink's owner and mode are
  not compared, and a target that does not exist is no difference.
- The second list is what `install` leaves alone: a directory without a
  `.meta` line whose owner or mode is not the default.
- `-v` prints the machine's files, secrets and all, except the known
  values of a template; a binary file is only named. An agent runs it on a
  real machine only when the owner asks.
- `--root DIR` compares `DIR` instead of `/`.

## Restoring a backup

```sh
uv run dotfiles restore --dry-run        # what it would put back
uv run dotfiles restore                  # the last run
uv run dotfiles restore 20261011-213000  # that run
uv run dotfiles restore /etc/x /etc/y    # only these files, from the last run
```

A run's directory in `.backups/<host>/` is laid out like a host, its
`.meta` holding a line for every file, so `restore` puts it back the way
`install` puts a host: each file at its path with its old owner and mode,
printing the same lines, a symlink put back as a symlink. The files it
replaces are kept in a new run, so a restore can be undone too. Files the
run does not hold are left alone.

- An argument that starts with `/` is a path; the other one, if any, is the
  run. A path the run does not hold is an error.
- `--dry-run` and `--root DIR` work as they do for `install`, and so do the
  host's `.hooks`.

## Removing backups

```sh
uv run dotfiles cleanup --dry-run      # what it would remove
uv run dotfiles cleanup                # every backup
uv run dotfiles cleanup --keep 3       # all but the last 3 runs of each host
uv run dotfiles cleanup --older-than 30   # the runs older than 30 days
```

It removes whole runs, the directories under `.backups/<host>/`, and
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
