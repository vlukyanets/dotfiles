# fcitx5

[`.chezmoiscripts/run_once_before_19-configure-fcitx5.sh.tmpl`](../../.chezmoiscripts/run_once_before_19-configure-fcitx5.sh.tmpl)
installs `fcitx5`, `fcitx5-gtk`, and `fcitx5-qt` when `fcitx5.enabled` is
true (default `false` — the script exits immediately otherwise), plus
`fcitx5-pinyin` when `"chinese"` is also in
[`locale.languages`](locale.md#languages). The same flag gates
`dot_config/fcitx5/*` in `.chezmoiignore.tmpl` — the same "one flag
controls both the install and the dotfile" shape as
[`shell.zsh.enabled`](shell.md) — and, in
[niri's config](desktop/niri.md#fcitx5), the IM environment variables,
spawning fcitx5 at startup, and syncing its active input method on layout
switch.

## `dot_config/fcitx5/config`

Ported as-is from the old `__dotfiles` repo, not templated. Sets three
things niri's `switch-layout.sh.tmpl` logic depends on being true, not
just cosmetic defaults:

- `ActiveByDefault=False` — fcitx5 starts inactive; `switch-layout.sh.tmpl`
  turns it on/off explicitly (`fcitx5-remote -o`/`-c`) rather than fcitx5
  guessing per-window.
- `ShareInputState=All` — activation state is shared across every window
  instead of per-window, so those same `-o`/`-c` calls take effect
  globally on a single layout switch.
- `ShowInputMethodInformation`/`ShowFirstInputMethodInformation=False` —
  suppresses fcitx5's own switch-notification popup, since niri's
  `Mod+Space` bind already retitles the hotkey overlay
  (`hotkey-overlay-title="Switch Language"`) instead.

## `dot_config/fcitx5/profile.tmpl`

Lists which input methods fcitx5 actually has available —
`fcitx5-remote -s <name>` (used by
[`switch-layout.sh.tmpl`](desktop/niri.md#fcitx5)) can only select an
input method this profile declares. Built from
[`locale.languages`](locale.md#languages) via the same
[`.chezmoitemplates/language-codes`](../../.chezmoitemplates/language-codes)
mapping `config.kdl.tmpl` and `switch-layout.sh.tmpl` use for their own
lists, so all three stay in agreement without hand-syncing separate
per-file lists — see [niri](desktop/niri.md#keyboard-layouts-and-localelanguages)
for why that matters. `DefaultIM` is set to whichever input method comes
first in `locale.languages`' order.

Unlike the old `__dotfiles` version — a `run_onchange_after_*` script that
wrote `~/.config/fcitx5/profile` imperatively and force-restarted a live
fcitx5 daemon (`pkill -KILL fcitx5; fcitx5 -d`) — this is a plain chezmoi
dotfile, the same as every other app config in this repo. A running
session doesn't pick up a `locale.languages` change until fcitx5 is
restarted (next login, or manually), the same caveat
[Firefox](browsers/firefox.md) already has for `browsers.<name>.settings`
changes not reaching an already-open profile.

## Not yet ported

`dot_config/fcitx5/conf/classicui.conf` (theme/font) and the
`FluentDark-solid` theme it points at, from the old `__dotfiles` repo,
aren't included — fcitx5 runs with its own built-in default UI theme
instead. Cosmetic only; doesn't affect anything `switch-layout.sh.tmpl`
depends on.
