# Desktop

[`.chezmoiscripts/run_once_before_13-configure-desktop.sh.tmpl`](../../.chezmoiscripts/run_once_before_13-configure-desktop.sh.tmpl)
is gated behind `desktop.enabled` (default `false`) — hosts that leave it
unset skip it entirely and no desktop packages are touched.

When enabled, `desktop.environment` picks which desktop environment to
install. It's a required field once `desktop.enabled = true`: unlike every
other opt-in flag in this repo, there's no reasonable "do nothing" default
for a host that asked for a desktop, so the script exits with an error
instead of silently installing nothing when it's left unset or set to a
value it doesn't recognize. The only value currently implemented is
`"niri"` — a Wayland compositor. Enabling it installs `niri`,
`xwayland-satellite`, `xdg-desktop-portal-gtk`, `xdg-utils`,
`wl-clipboard`, and `gnome-themes-extra` — the minimum to get niri itself
running under Wayland with a working dark GTK theme (see below). Anything
else niri-adjacent (a brightness key binding via `brightnessctl`, a
notification daemon, etc.) goes in [`cli_tools.enabled`](cli-tools.md) per
host, not hardcoded here.

`gnome-themes-extra` provides the `Adwaita-dark` GTK3 theme variant, which
the script then sets as the session default via `gsettings set
org.gnome.desktop.interface color-scheme/gtk-theme` — the *persistent*
half of dark theming (read by GTK apps through the dconf-backed
`org.gnome.desktop.interface` schema, including ones that don't look at
[niri's `GTK_THEME` environment variable](desktop/niri.md) directly, e.g.
via `xdg-desktop-portal-gtk`'s file picker). This needs a running user
D-Bus/dconf session to actually persist — true whenever this script runs
from an already-logged-in terminal, the normal case for `chezmoi apply`.

This script only installs the compositor itself — it has no opinion on how
you log into it. See [Greeter](greeter.md) for `greetd`/`tuigreet` (or
`noctalia-greeter`) setup, which is a separate, top-level concern from
`desktop.*`.

`desktop.niri.shell` is only read when `desktop.environment = "niri"` — it's
ignored otherwise. It picks a shell/bar layer to install on top of the bare
compositor. Default `""` installs niri with nothing on top. The only value
currently implemented is `"noctalia"`, which installs the single `noctalia`
package (the desktop shell's own official package, not the older AUR
`noctalia-shell` quickshell config). As with `desktop.environment`, a
non-empty value the script doesn't recognize is an error, not a silent
no-op.

Adding a second desktop environment means teaching this script a new `{{ if
eq .desktop.environment "..." }}` branch (and, if it has its own shell/bar
options, a new `desktop.<environment>.*` sub-table next to `desktop.niri.*`
— see [`.hosts.toml`](../../.hosts.toml)'s comment block for the pattern).

## Per-environment docs

- [niri](desktop/niri.md) — `dot_config/niri/*`, the compositor config
  itself (this page only covers installing the package)
- [noctalia](desktop/noctalia.md) — `dot_local/state/noctalia/settings.toml`,
  the shell's own settings file (this page only covers installing the
  package)
