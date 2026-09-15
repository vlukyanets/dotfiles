# dotfiles

Personal dotfiles for multiple machines, managed with [chezmoi](https://www.chezmoi.io/).

## Prerequisites

- [git](https://git-scm.com/)
- [chezmoi](https://www.chezmoi.io/install/)

## Conventions

**`SUDO_CMD`** — the privilege-escalation command used everywhere in this
repo (`dot_zshrc.tmpl`'s `update` alias, `.chezmoiscripts/*`). There's no
real cross-tool standard for this (checked sudo/doas, doas-sudo-shim,
topgrade — which only exposes it as a config-file option), so this repo
defines its own: every script/alias reads `${SUDO_CMD:-sudo}`, so exporting
`SUDO_CMD=doas` (in a profile sourced before `~/.zshrc`, or in the
environment a `chezmoi apply` run inherits) switches every one of them over
without touching this repo.

## How host config works

Machines are declared once in **[`.hosts.toml`](.hosts.toml)**,
keyed by hostname:

```toml
[hyper-lin]
```

The name deliberately avoids chezmoi's own `.chezmoidata` prefix. A file
named that way gets auto-merged into *every* template's top-level data on
every run — which here would mean every host's config (not just the one
being applied) becomes visible to every template, even though none of them
would use it. `.hosts.toml` is instead read explicitly, only by
`.chezmoi.toml.tmpl`, so the one host being applied is the only thing that
was ever exposed anywhere.

A host entry can be empty — its presence in the file is what marks the
machine as known. There's no shared `[default]` table; every field's
fallback lives in `.chezmoi.toml.tmpl` instead, and a host only needs a
sub-table for what it wants to override, e.g.:

```toml
[homelab.pkg-mgmt.makepkg]
jobs = "2"
```

**[`.chezmoi.toml.tmpl`](.chezmoi.toml.tmpl)** runs once at `chezmoi init`
time, looks up the current machine by hostname, and flattens its entry
(falling back to the hardcoded default for anything unset) into plain
template variables saved to `~/.config/chezmoi/chezmoi.toml`:

| variable                        | meaning                                                |
|-----------------------------------|-----------------------------------------------------------|
| `.hostname`                        | machine hostname                                           |
| `.git.user.name`                   | git user.name                                              |
| `.git.user.email`                  | git user.email (no default — empty unless a host sets one) |
| `.pkg_mgmt.pacman.parallel_downloads` | pacman.conf `ParallelDownloads`                         |
| `.pkg_mgmt.makepkg.jobs`           | makepkg.conf `MAKEFLAGS="-j<value>"` build parallelism      |
| `.pkg_mgmt.reflector.*`            | reflector.conf flags (save, country, protocol, latest, sort, age, download_timeout) |
| `.pkg_mgmt.reflector.timer.*`      | reflector.timer override (on_calendar, on_boot_sec)         |
| `.pkg_mgmt.aur.enabled`            | whether to build and install paru from the AUR              |
| `.locale.*`                        | locale.conf LANG, locale.gen entries, vconsole KEYMAP, timezone |
| `.services.enabled`                | systemd units to `enable --now`                             |
| `.services.packages`                | unit → pacman packages that provide it                      |
| `.shell.zsh.enabled`                | whether to install zsh and make it the login shell           |
| `.shell.zsh.oh_my_zsh.enabled`      | whether to also install oh-my-zsh, powerlevel10k, and the zsh plugins dot_zshrc.tmpl expects |

(Source data uses `pkg-mgmt` with a hyphen; the generated `[data]` uses
`pkg_mgmt` with an underscore instead, because a hyphen can't appear in a Go
template field name — see the comment in `.chezmoi.toml.tmpl`.)

`makepkg.jobs` accepts a plain integer ("4"), a percentage of CPU count
("20%", floored and clamped up to a minimum of 1 whenever the percentage is
> 0%, resolved by `resolve_parallel()` in the script below), or a raw shell
expression like `"$(nproc)"` (the default) — which, unlike the other two
forms, is written through unresolved and evaluated fresh at every build
rather than once at apply time, since `makepkg.conf` is sourced as shell.

`pacman.parallel_downloads` is a fixed integer only — `pacman.conf` isn't
shell, so there's no later point where a percentage or shell expression
could still be evaluated. `chezmoi init` fails loudly (rather than silently
misbehaving) if given one.

Every other template in the repo can branch on these, plus chezmoi's built-in
`.chezmoi.hostname`, `.chezmoi.os`, `.chezmoi.arch`, `.chezmoi.osRelease.id`,
etc. See [`dot_zshrc.tmpl`](dot_zshrc.tmpl) and
[`dot_gitconfig.tmpl`](dot_gitconfig.tmpl) for worked examples of branching
on `.chezmoi.*`, and
[`.chezmoiscripts/run_once_before_00-configure-pacman.sh.tmpl`](.chezmoiscripts/run_once_before_00-configure-pacman.sh.tmpl)
/
[`.chezmoiscripts/run_once_before_01-configure-reflector.sh.tmpl`](.chezmoiscripts/run_once_before_01-configure-reflector.sh.tmpl)
for scripts that use the host-configurable values above. The reflector
script installs `reflector`, writes its flags to
`/etc/xdg/reflector/reflector.conf` (the `@`-argfile `reflector.service`
already reads), drops an override at
`/etc/systemd/system/reflector.timer.d/override.conf` for the timer's
`OnCalendar`/`OnBootSec`, enables `reflector.timer`, and runs `reflector`
once immediately so the mirrorlist isn't stale until the timer's first
fire. `reflector.service` itself just runs `reflector @/etc/xdg/reflector/reflector.conf`
— every field written into that one file, `--save` included, is what both
the one-time run and every later timer-triggered run use, with nothing
timer-specific to configure beyond the `OnCalendar`/`OnBootSec` override.
`pkg_mgmt.reflector.save` is also read by the pacman script's multilib
`Include=` line, so the two scripts always agree on which mirrorlist file
is in play — change it once, in `.hosts.toml`, not in either script.

[`.chezmoiscripts/run_once_before_02-configure-aur.sh.tmpl`](.chezmoiscripts/run_once_before_02-configure-aur.sh.tmpl)
builds and installs [paru](https://github.com/Morganamilo/paru) from the AUR,
gated entirely behind `pkg_mgmt.aur.enabled` (default `false`) — hosts that
leave it unset skip the script without touching the network. When enabled,
it's still a no-op if `paru` is already on `PATH`, otherwise it installs
`base-devel`/`git`, clones `paru` into a scratch directory, and runs
`makepkg -si` there (unprefixed by `SUDO_CMD`, since `makepkg` refuses to run
as root — see the comment in the script).

[`.chezmoiscripts/run_once_before_03-configure-locale.sh.tmpl`](.chezmoiscripts/run_once_before_03-configure-locale.sh.tmpl)
enables each entry in `locale.locales` in `/etc/locale.gen` (uncommenting it
if it's already there commented out, appending it otherwise) and runs
`locale-gen`, then writes `/etc/locale.conf` (`LANG`) and `/etc/vconsole.conf`
(`KEYMAP`) from `locale.lang`/`locale.keymap`, and finally symlinks
`/etc/localtime` to `locale.timezone` under `/usr/share/zoneinfo/` and runs
`hwclock --systohc` to match. `locale.locales` and `locale.lang` are
independent fields — `locales` only controls what `locale-gen` compiles, so
if it doesn't already include whatever `lang` names, `LANG` ends up pointing
at a locale that was never generated.

[`.chezmoiscripts/run_once_before_04-configure-services.sh.tmpl`](.chezmoiscripts/run_once_before_04-configure-services.sh.tmpl)
runs `systemctl enable --now` for each unit listed in `services.enabled`
(default `[]` — the script exits immediately without touching systemd on
hosts that don't set it). Before enabling anything, it looks up each unit
in `services.packages` (unit name → list of pacman packages that provide
it), collects the packages for every enabled unit into one deduplicated
list, and installs them in a single `pacman -S --needed` call — a unit with
no entry in `services.packages` is just enabled as-is, nothing installed.
`enable --now` is idempotent on its own, so re-running this script (or
applying on a host where a unit is already enabled and running) is always a
no-op for that unit.

[`.chezmoiscripts/run_once_before_05-configure-shell.sh.tmpl`](.chezmoiscripts/run_once_before_05-configure-shell.sh.tmpl)
is gated behind `shell.zsh.enabled` (default `false`) the same way the AUR
script is gated behind `pkg_mgmt.aur.enabled` — hosts that leave it unset
skip it entirely. When enabled, it installs `zsh` and (if it isn't already
the login shell) runs `chsh` to make it one. If `shell.zsh.oh_my_zsh.enabled`
is also set, it further clones oh-my-zsh, the `powerlevel10k` theme, and the
`zsh-autosuggestions`/`zsh-syntax-highlighting` plugins into `$ZSH_CUSTOM`.
Every clone is skipped if its directory already exists, so re-running (or
applying to a machine that already has these installed by hand) is a no-op.

[`.chezmoiignore.tmpl`](.chezmoiignore.tmpl) skips `~/.zshrc` entirely on any
host with `shell.zsh.enabled` unset or `false` — there's no point writing a
zsh config on a host that isn't opting into zsh. On a host that does,
[`dot_zshrc.tmpl`](dot_zshrc.tmpl) itself further branches on
`shell.zsh.oh_my_zsh.enabled`: the oh-my-zsh/Powerlevel10k block is only
rendered into `~/.zshrc` when that's also set, matching exactly what
`05-configure-shell.sh.tmpl` installs — a host with `shell.zsh.enabled` but
not the oh-my-zsh flag gets a plain, working `~/.zshrc` with none of that
theming.

[`.chezmoiignore.tmpl`](.chezmoiignore.tmpl) is where to skip whole files on
hosts where they don't apply.

Running `chezmoi init` on a machine that isn't registered fails outright —
there's no interactive prompt and no silent all-defaults fallback. Add a
`[<hostname>]` table to `.hosts.toml` (it can be empty) first.

**`.chezmoi.toml.tmpl` only runs at `chezmoi init`, not at `chezmoi apply`.**
Editing `[<host>.pkg-mgmt.*]` (or any other field it reads) in
`.hosts.toml` does *not* take effect on the next plain `apply` — the
already-generated `~/.config/chezmoi/chezmoi.toml` is reused as-is. Re-run
`chezmoi init` (safe to repeat; it doesn't touch anything outside that one
config file) to regenerate it, then `apply` — or just `chezmoi init --apply`
to do both in one step.

## Adding a new machine

1. Add a `[<hostname>]` table to `.hosts.toml` (a template is already
   there, commented out) from wherever's convenient, then commit and push
   it:
   ```sh
   chezmoi cd && git add .hosts.toml && git commit -m "add host <name>" && git push
   ```
   This has to happen *before* step 2 — `chezmoi init` on the new machine
   clones the repo fresh from the remote, and now fails outright if that
   clone doesn't already have the new hostname registered.
2. On the new machine:
   ```sh
   sh -c "$(curl -fsLS get.chezmoi.io)" -- init --apply vlukyanets
   ```
   (already have chezmoi? just `chezmoi init --apply vlukyanets`)

## Everyday commands

| command                    | what it does                                         |
|-----------------------------|-------------------------------------------------------|
| `chezmoi edit ~/.zshrc`     | open the source template for a managed file           |
| `chezmoi diff`              | preview what `apply` would change                     |
| `chezmoi apply`             | render templates and write them into `$HOME`          |
| `chezmoi cd`                | drop into the source dir (this repo) as a subshell     |
| `chezmoi update`            | `git pull` + `apply` in one step                       |
| `chezmoi status`            | show which managed files differ from source            |

## Layout reference

- `.hosts.toml` — per-host config, keyed by hostname (data, not templates)
- `.chezmoi.toml.tmpl` — turns a host's entry into template variables, defaults included
- `.chezmoiignore.tmpl` — per-host file exclusions
- `dot_*` / `private_dot_*` — become `~/.*` on `apply` (chezmoi's naming
  convention: `dot_` → `.`, `private_` → mode `0600`)
- `.chezmoiscripts/run_once_*` — one-time setup scripts (package installs,
  etc.); `run_once_` means chezmoi runs it once per content hash, re-running
  automatically whenever the script's content changes
