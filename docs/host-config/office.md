# Office

[`.chezmoiscripts/run_once_before_22-configure-office.sh.tmpl`](../../.chezmoiscripts/run_once_before_22-configure-office.sh.tmpl)
installs whatever's listed under `office.<name>` with `enabled = true`
(default `{}` — no entries, script exits immediately), the same shape as
[Terminals](terminals.md) and [Password managers](password-managers.md).
`<name>` itself is just a label, not read anywhere except log output — pick
anything, e.g. `"onlyoffice"`.

Unlike those two, each entry also has a `source` field, one of:

- `"pacman"` (default) — installed with `pacman -S --needed`.
- `"aur"` — installed with `paru -S --needed` instead. Requires
  `pkg-mgmt.aur.enabled = true` on this host (see [AUR/paru](aur.md)) — the
  script exits with an error if it isn't, rather than silently falling back
  to pacman. Needed for office suites that aren't in the official
  repositories at all, e.g. `onlyoffice-bin`.

Each entry's own `packages` list (default `[]` — enabling an entry with none
listed just errors out on pacman/paru's own "no targets specified") is
installed with its own single call.

An entry can be present with `enabled = false` — e.g. while trying out a
replacement without uninstalling the current one.
