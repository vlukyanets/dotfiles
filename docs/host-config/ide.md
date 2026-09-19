# IDE

[`.chezmoiscripts/run_once_before_25-configure-ide.sh.tmpl`](../../.chezmoiscripts/run_once_before_25-configure-ide.sh.tmpl)
installs whatever's listed under `ide.<name>` with `enabled = true`
(default `{}` — no entries, script exits immediately), the same
`enabled`/`source`/`packages` shape as [Office](office.md) and
[Development](development.md). `<name>` is just a label, not read anywhere
except log output — pick anything, e.g. `"vscode"`.

`source` is one of:

- `"pacman"` (default) — installed with `pacman -S --needed`.
- `"aur"` — installed with `paru -S --needed` instead. Requires
  `pkg-mgmt.aur.enabled = true` on this host (see [AUR/paru](aur.md)) — the
  script exits with an error if it isn't, rather than silently falling back
  to pacman.

Each entry's own `packages` list (default `[]` — enabling an entry with none
listed just errors out on pacman/paru's own "no targets specified") is
installed with its own single call. An entry can be present with `enabled
= false` — e.g. while trying out a replacement without uninstalling the
current one.

`enabled` gates two things at once, per entry, the same "one flag controls
both the install and the dotfile" shape as
[`terminals.<name>.enabled`](terminals.md): this script's install, and —
where that IDE has one — its own dotfile in `.chezmoiignore.tmpl`.

`ide.vscode` additionally takes a `profiles` list — which of the VS Code
profiles defined in `dot_config/Code/User/profiles.json` (extension sets
and settings overrides) to set up on this host, all of them when unset.
They're applied by a script of their own (`run_once_before_27`) since
the CLI can't create profiles. See
[Visual Studio Code](ide/vscode.md#profiles); any other `ide.<name>`
ignores the field.

## Per-IDE docs

- [Visual Studio Code](ide/vscode.md)
- [Neovim](ide/neovim.md)
