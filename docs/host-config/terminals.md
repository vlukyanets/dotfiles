# Terminals

[`.chezmoiscripts/run_once_before_19-configure-terminals.sh.tmpl`](../../.chezmoiscripts/run_once_before_19-configure-terminals.sh.tmpl)
installs whatever's listed under `terminals.<name>` with `enabled = true`
(default `{}` — no entries, script exits immediately), the same shape as
[Browsers](browsers.md). Each entry's own `packages` list (default `[]` —
enabling an entry with none listed just errors out on pacman/paru's own "no
targets specified") is installed with its own call. `<name>` itself is just
a label, same as `browsers.<name>` — pick anything, e.g. `"kitty"`. An
entry can be present with `enabled = false` — e.g. while trying out a
replacement without uninstalling the current one.

`source` (default `"pacman"`) picks `pacman -S --needed` or, with `"aur"`,
`paru -S --needed` instead — same field, same shape, as
[`browsers.<name>.source`](browsers.md), including the
`pkg-mgmt.aur.enabled = true` requirement.

## Per-app config

Each `terminals.<name>` table is also where that terminal's own config
knobs live, added as named fields on demand as a given terminal actually
needs them (e.g. a future `font_size`). There's no shared, generic
`settings` blob the way [`browsers.<name>.settings`](browsers.md#settings)
works — that shape exists there because every browser listed is
Firefox-based and shares one config mechanism (`policies.json`). Terminal
emulators don't share a config format the same way, so a generic
pass-through wouldn't have anywhere uniform to land; each terminal's own
`dot_config/<name>/*.tmpl` reads its own fields directly, following the
same "named field with a documented default" shape every other feature in
`.chezmoi.toml.tmpl` already uses (e.g. `zram.size`, `ssh.permit_root_login`).

`enabled` is the one field every entry shares. It gates two things at
once, the same "one flag controls both the install and the dotfile" shape
as [`shell.zsh.enabled`](shell.md): this script's install, and — per
terminal, in `.chezmoiignore.tmpl` — whether that terminal's dotfile is
written at all.

## Per-terminal docs

- [kitty](terminals/kitty.md)
