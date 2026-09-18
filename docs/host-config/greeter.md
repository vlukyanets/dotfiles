# Greeter

[`.chezmoiscripts/run_once_before_14-configure-greeter.sh.tmpl`](../../.chezmoiscripts/run_once_before_14-configure-greeter.sh.tmpl)
is gated behind `greeter.type` (default `""`) — hosts that leave it unset
skip it entirely and `greetd` is never installed. It's a separate,
top-level concern from [`desktop.*`](desktop.md): nothing here checks
which desktop environment (if any) is enabled, since `greetd` itself
doesn't care what it's handing off to — it just needs something under
`/usr/share/xsessions` or `/usr/share/wayland-sessions` to offer. In
practice, only [niri](desktop.md) provides one of those right now, so a
non-empty `greeter.type` is only useful alongside `desktop.environment =
"niri"`, but the two aren't validated against each other.

`greeter.type = "tuigreet"` installs `greetd-tuigreet` from the configured
pacman repositories — its own `Depends=` lists `greetd`, so `pacman -S
--needed` pulls that in too, without listing it separately — and points
`/etc/greetd/config.toml`'s `[default_session]` at `tuigreet --remember
--remember-session --sessions /usr/share/xsessions:/usr/share/wayland-sessions`.

`greeter.type = "noctalia-greeter"` installs
[noctalia-greeter](https://github.com/noctalia-dev/noctalia-greeter) via
`paru -S` instead — its AUR `Depends=` lists `greetd` too, so this pulls
it in the same way, entirely through the AUR helper rather than split
across `pacman` and `paru`. It points `[default_session]` at
`noctalia-greeter-session` (the session wrapper the greetd docs require —
not the `noctalia-greeter` binary itself). It requires
[`pkg-mgmt.aur.enabled`](aur.md) `= true` on the same host; the script
exits with an error rather than silently falling back to `tuigreet` if
that isn't set — the two greeters are mutually exclusive (only one is ever
installed), and a missing AUR helper is never worked around by quietly
substituting the other one.

Either way, the script enables `greetd.service`. Any value other than
`""`, `"tuigreet"`, or `"noctalia-greeter"` is an error, not a silent
no-op.

## Per-greeter options

`greeter.noctalia-greeter.session` and `greeter.noctalia-greeter.user`
(read only when `greeter.type = "noctalia-greeter"`) are appended to
`noctalia-greeter-session`'s command line after a `--` separator, which
greetd itself never sees — they're `noctalia-greeter`'s own flags, not
greetd's. `session` forces a specific Wayland session name (e.g. `"niri"`)
instead of showing noctalia-greeter's session picker; `user` skips the
user list too and goes straight to the password prompt for that login.
Both default to `""` (picker/list shown). `tuigreet` has no per-greeter
options yet — add a matching `greeter.tuigreet.*` table (and a
`[<host>.greeter.tuigreet]` doc block in
[`.hosts.toml`](../../.hosts.toml)) if that changes.

## AUR packages and `pkg-mgmt.aur.enabled`

`greeter.type = "noctalia-greeter"` is this repo's first host-config value
that pulls a package from the AUR outside the [AUR/paru](aur.md) script
itself. If a host sets it without `pkg-mgmt.aur.enabled = true`, the script
fails loudly (see above) instead of either silently installing `tuigreet`
instead or, worse, running head-first into a `paru: command not found`.
This is deliberately checked here rather than aborting `chezmoi init`
outright over it (the way an unregistered hostname does in
`.chezmoi.toml.tmpl`): script ordering already guarantees
`run_once_before_02-configure-aur.sh.tmpl` runs, and would itself abort the
whole `apply` under `set -eu`, before this script ever gets to run whenever
`pkg-mgmt.aur.enabled` is actually `true` — so by the time this script's
own `paru -S` line is reached, `paru` failing to be on `PATH` can only mean
the host left AUR turned off on purpose, which is exactly what this check
reports.
