# noctalia

[`dot_local/state/noctalia/settings.toml.tmpl`](../../../dot_local/state/noctalia/settings.toml.tmpl)
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

What's intentionally set here, all overrides of built-in defaults that
`noctalia config export full` dumps (so each key only overrides the one
field actually changed, not the whole table):

- `bar.default.end` puts the `keyboard_layout` widget (showing the active
  input method/layout) first among the right-hand bar widgets.
- `bar.default.start` drops the `wallpaper` picker from the default
  `launcher, wallpaper, workspaces` — the picker is still reachable from
  the control center.
- `bar.default.margin_ends = 0` makes the bar span the full screen width;
  the default is `100`, i.e. a 100px inset on each end.
- `bar.default.font_scale = 1.1` — bar text 10% larger than default. This
  is the bar's own knob; the shell-wide one is top-level `ui_scale`.
- `shell.font_family` is the one templated value, and the reason the file
  is a `.tmpl`: it's `desktop.niri.noctalia.font` from `.hosts.toml`, or
  noctalia's own default `sans-serif` when that's unset. It's the whole
  shell's font (bar, launcher, panels), not just the bar's. The package
  behind the font goes in the sibling `desktop.niri.noctalia.font_package`,
  which [the desktop script](../desktop.md) installs in the same `pacman`
  call as `noctalia` — so the font is noctalia's own dependency, not
  something [`fonts.enabled`](../fonts.md) has to happen to include. On
  `hyper-lin` it's `FiraCode Nerd Font Propo` / `ttf-firacode-nerd`: the
  `Propo` variant is the proportional cut of the Nerd Font, so UI text
  isn't spaced like a terminal. `ttf-firacode-nerd` is also in
  `fonts.enabled` there for kitty; `pacman --needed` makes the double
  listing harmless. A `font` whose package isn't installed isn't an error
  — fontconfig substitutes its default, the usual "missing font isn't an
  error" outcome `fonts.md` describes.
- `[theme]` is `desktop.niri.noctalia.theme` from `.hosts.toml`:
  `source` and `mode` are written as-is, and `name` lands in whichever
  key that source reads — `builtin` for `"builtin"`, `community_palette`
  for `"community"`, `wallpaper_scheme` for `"wallpaper"` — or nothing at
  all when `name` is unset, leaving noctalia's own pick for that source.
  The defaults (`builtin` / `""` / `dark`) reproduce noctalia's stock
  look, so a host that doesn't set the table gets what it got before.
  `hyper-lin` uses the `Cyberpunk` community palette; the gallery is
  [noctalia.dev/palettes](https://noctalia.dev/palettes) (the names
  there are the `community_palette` ids), and `noctalia msg
  color-scheme-set community "<name>"` tries one live before it goes
  into `.hosts.toml` — with the caveat above that it rewrites this file,
  so the next `chezmoi apply` asks once. Nothing validates the name; a
  wrong one makes noctalia fall back to its default palette, not fail.
  `theme.templates` (noctalia generating colour schemes for kitty, niri,
  fcitx5, Neovim and some seventy other apps) is deliberately left at
  its default, off: those files are chezmoi-managed here, and noctalia
  writing into them would make every apply a conflict. Wiring that up —
  noctalia writing a side file that `kitty.conf` includes and
  `.chezmoiignore` skips — is a separate piece of work.

`noctalia msg config-reload` picks up an edit to this file without a
compositor restart. Note that `chezmoi apply` reads the source dir it's
configured with (`chezmoi source-path`, normally
`~/.local/share/chezmoi`), so to try a change from a different checkout
pass `--source <that checkout>` explicitly.

The widgets in `bar.default.end` are clients, not providers: `bluetooth` talks
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
