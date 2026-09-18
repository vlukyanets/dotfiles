# Password managers

[`.chezmoiscripts/run_once_before_20-configure-password-managers.sh.tmpl`](../../.chezmoiscripts/run_once_before_20-configure-password-managers.sh.tmpl)
installs whatever's listed under `password_managers.<name>` with
`enabled = true` (default `{}` — no entries, script exits immediately),
the same shape as [Terminals](terminals.md). Each entry's own `packages`
list (default `[]` — enabling an entry with none listed just errors out
on pacman's own "no targets specified") is installed with its own
`pacman -S --needed` call. `<name>` itself is just a label, same as
`terminals.<name>` — pick anything, e.g. `"rbw"`. An entry can be present
with `enabled = false` — e.g. while trying out a replacement without
uninstalling the current one.

## Per-manager config

Each `password_managers.<name>` table is also where that program's own
config knobs live, added as named fields on demand, the same "no shared
generic settings blob" shape as [`terminals.<name>`](terminals.md#per-app-config)
— every password manager's config file has its own format, so there's
nowhere uniform for a pass-through to land.

`enabled` is the one field every entry shares. It gates two things at
once, the same "one flag controls both the install and the dotfile" shape
as [`shell.zsh.enabled`](shell.md): this script's install, and — per
manager, in `.chezmoiignore.tmpl` — whether that manager's dotfile is
written at all.

## Per-manager docs

- [rbw](password-managers/rbw.md)
