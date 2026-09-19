# noctalia

[`dot_local/state/noctalia/settings.toml`](../../../dot_local/state/noctalia/settings.toml)
is written whenever `desktop.niri.shell = "noctalia"` — see
[Desktop](../desktop.md). `.chezmoiignore.tmpl` skips
`~/.local/state/noctalia` entirely otherwise, the same "one flag controls
both the install and the dotfile" shape as [`fcitx5.enabled`](../fcitx5.md).

It lives under `~/.local/state` (XDG state, not `~/.config`) because
that's where noctalia itself puts it — not a location this repo chose.
That matters because noctalia treats this file as both config *and*
state: it rewrites it whenever a setting changes through its own GUI
(wallpaper picker, theme picker, the lockscreen/desktop widget editors,
etc.), not just when `chezmoi apply` runs. A `chezmoi apply` after such a
GUI change reverts it back to whatever's committed here — same caveat
`fcitx5.md` and `browsers.<name>.settings` already have for a live app
overwriting its own dotfile; port the change back into this file if it
should stick.

Currently the only thing intentionally set here is `bar.default.end`,
which puts the `keyboard_layout` widget (showing the active input
method/layout) first among the right-hand bar widgets — `noctalia config
export full` is what dumped the rest of the built-in defaults for that
table (`start`, `center`, and everything else `bar.default` accepts) so
that adding `keyboard_layout` only overrides the one field actually
changed, not the whole bar. `noctalia msg config-reload` picks up an edit
to this file without a compositor restart.

The widgets in that list are clients, not providers: `bluetooth` talks
to BlueZ over D-Bus (`org.bluez`) and `network` to NetworkManager, and
neither pulls its daemon in. A host that wants the bluetooth toggle to do
anything needs `bluetooth` in [`services.enabled`](../services.md) with
`bluez` (and `bluez-utils` for `bluetoothctl`) in `services.packages` —
without it the widget renders, the switch flips, and nothing happens,
even with the adapter present and rfkill clear.

Everything else in the file — `control_center.calendar.show_week_numbers`,
`lockscreen_widgets`, `wallpaper.default`/`wallpaper.last` — is whatever
noctalia's GUI had already written on `hyper-lin` at the time this file
was captured, not something explicitly configured here. In particular
`lockscreen_widgets.widget."lockscreen-login-box@eDP-1"` hardcodes an
output name (`eDP-1`) and pixel geometry (`1920x1080`) tied to that one
machine's screen — meaningless, and safe to ignore, on a host with a
different monitor, since `lockscreen_widgets.enabled` is `false` there
anyway.
