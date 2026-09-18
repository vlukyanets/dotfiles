# niri

[`dot_config/niri/config.kdl.tmpl`](../../../dot_config/niri/config.kdl.tmpl),
ported from the old `__dotfiles` repo, is written whenever
`desktop.enabled = true` and `desktop.environment = "niri"` — see
[Desktop](../desktop.md). `.chezmoiignore.tmpl` skips `~/.config/niri`
entirely otherwise, the same "one flag controls both the install and the
dotfile" shape as [`shell.zsh.enabled`](../shell.md).

Two companion scripts live alongside it:

- [`executable_lock-screen.sh`](../../../dot_config/niri/executable_lock-screen.sh)
  — resets the keyboard layout to index 0 (English), then locks the
  session via `noctalia msg session lock`, optionally powering off
  monitors first (`--monitors-off`).
- [`executable_switch-layout.sh.tmpl`](../../../dot_config/niri/executable_switch-layout.sh.tmpl)
  — cycles (or jumps to) a niri keyboard layout and syncs fcitx5's active
  input method to match, bound to `Mod+Space` in `config.kdl.tmpl`.

## Keyboard layouts and `locale.languages`

`config.kdl.tmpl`'s `input.keyboard.xkb.layout` is built from
[`locale.languages`](../locale.md#languages), and `switch-layout.sh.tmpl`'s
fcitx5 input-method list is built from the same field — both by ranging
over `locale.languages` in order and looking each entry up in
[`.chezmoitemplates/language-codes`](../../../.chezmoitemplates/language-codes),
a shared `language → {xkb, fcitx5}` mapping included by both templates.
This is deliberate: the two lists have to stay index-aligned (niri's
active layout is reported as a numeric index, not a name — see below), and
building both from one shared source in the same order guarantees that
without hand-syncing two independently-maintained lists.

`switch-layout.sh.tmpl` gets niri's current layout with `niri msg -j
keyboard-layouts`, not the earlier `__dotfiles` version's `niri msg
keyboard-layouts | grep '\*' | cut -d' ' -f4-`. The JSON form returns
`{"names": [...], "current_idx": N}` directly — `current_idx` is used to
index straight into the fcitx5 IM array built above, with no need to
match niri's human-readable layout name (e.g. `"English (US)"`) against
anything. The old text-parsing approach was fragile in two ways this
avoids: it depended on niri's table output staying in exactly the same
column format, and its `LAYOUT_MAP` was a second, separately-maintained
name → fcitx5-IM table that had no structural link to the xkb layout list
in `config.kdl.tmpl` — two lists that happened to agree, rather than one
list two files both read.

## fcitx5

`fcitx5.enabled` (see [`.hosts.toml`](../../../.hosts.toml)'s comment
block) gates every fcitx5-related line in both files: the
`GTK_IM_MODULE`/`QT_IM_MODULE`/`XMODIFIERS` environment variables and
`spawn-at-startup "fcitx5" "-d"` in `config.kdl.tmpl`, and the whole
IM-switching block in `switch-layout.sh.tmpl`. No script installs the
`fcitx5` package yet — that, plus its own `dot_config/fcitx5/*`, is a
separate, not-yet-ported feature. Until it lands, leave `fcitx5.enabled`
false; turning it on early just points GTK/Qt apps at an input method
daemon that isn't running.

## Hardware note

The `output "eDP-1"` / `output "HDMI-A-1"` blocks (mode, scale, position)
are specific to `hyper-lin`'s actual display hardware, carried over
as-is from `__dotfiles` (same physical machine). A different host enabling
niri would need to replace these with its own output names/modes — run
`niri msg outputs` under an already-running niri session (even with a
bare/default config) to find them.

## Dependencies

`config.kdl.tmpl`'s key binds spawn `playerctl` (media keys) and
`brightnessctl` (brightness keys) directly, and `switch-layout.sh.tmpl`
shells out to `jq`. None of these are installed by this script — like
other niri-adjacent tools, they're expected in that host's
[`cli_tools.enabled`](../cli-tools.md).
