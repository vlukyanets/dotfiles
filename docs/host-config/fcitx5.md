# fcitx5

[`.chezmoiscripts/run_once_before_19-configure-fcitx5.sh.tmpl`](../../.chezmoiscripts/run_once_before_19-configure-fcitx5.sh.tmpl)
installs `fcitx5`, `fcitx5-gtk`, `fcitx5-qt`, and `fcitx5-configtool` when
`fcitx5.enabled` is true (default `false` — the script exits immediately
otherwise), plus `fcitx5-chinese-addons` (pinyin and the other Chinese
input methods — there's no standalone `fcitx5-pinyin` package on Arch)
when `"chinese"` is also in [`locale.languages`](locale.md#languages). The
same flag gates
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

## Theme

[`dot_config/fcitx5/conf/classicui.conf`](../../dot_config/fcitx5/conf/classicui.conf)
points fcitx5's classic UI (the candidate-selection popup) at
`FluentDark-solid`, a dark theme ported as-is (including its PNG assets)
from the old `__dotfiles` repo to
[`dot_local/share/fcitx5/themes/FluentDark-solid/`](../../dot_local/share/fcitx5/themes/FluentDark-solid).
Both paths — `~/.config/fcitx5` and `~/.local/share/fcitx5` — are gated
on `fcitx5.enabled` in `.chezmoiignore.tmpl`, the theme living under the
latter since that's where fcitx5 itself looks for
`<XDG_DATA_HOME>/fcitx5/themes/<name>/theme.conf`. Cosmetic only — it
doesn't affect anything `switch-layout.sh.tmpl` depends on, unlike
`dot_config/fcitx5/config` above.

The same file also sets `PreferTextIcon=True` and
`ShowLayoutNameInIcon=True`, plus a larger `TrayFont`, so the system-tray
icon renders every input method — keyboard layouts and pinyin alike — as
a short text label (`US`/`RU`/`UA`/pinyin's own label) instead of a
generic keyboard icon that only visually changes between "inactive" and
"pinyin active". Without this, `keyboard-us`/`keyboard-ru`/`keyboard-ua`
have no distinct icon of their own in most icon themes, so the tray
can't otherwise show which of them is actually active.

## Cloud Pinyin

`fcitx5.cloudpinyin` (default `false`) turns on cloudpinyin: pinyin
candidates get topped up from an online backend, useful for names/slang/
rare words a local dictionary doesn't have. No separate package —
`libcloudpinyin.so` already ships inside `fcitx5-chinese-addons`
(`OnDemand=True`, dormant until switched on), so this flag only touches
config, not the install script.

- [`dot_config/fcitx5/conf/pinyin.conf.tmpl`](../../dot_config/fcitx5/conf/pinyin.conf.tmpl)
  — the pinyin addon's own config file, in fcitx5's own generated format
  (a `#`-commented description above each key, its default value also
  commented out unless actually set — same as what fcitx5 itself writes
  the first time it runs). Every key here is left exactly as fcitx5's own
  defaults except `CloudPinyinEnabled`, the one line templated straight
  from `fcitx5.cloudpinyin` and left uncommented (an active setting,
  same convention as the pre-existing `FirstRun=False` line below it) —
  keeping the rest of the file intact avoids silently wiping out fcitx5's
  own reference documentation of every other pinyin setting on every
  `chezmoi apply`.
- [`dot_config/fcitx5/conf/cloudpinyin.conf`](../../dot_config/fcitx5/conf/cloudpinyin.conf)
  — the backend's own settings, currently just `Backend=Baidu`. Shipped
  unconditionally alongside the rest of `dot_config/fcitx5/conf/` (dormant,
  same as the addon itself, when the flag above is off) rather than
  gated separately — one inert file is simpler than a second
  `.chezmoiignore.tmpl` rule for what `CloudPinyinEnabled` already
  controls. Google's backend needs a VPN from most networks that also
  need cloudpinyin's help; Baidu doesn't, hence the default.

Every pinyin syllable typed leaves the machine for whichever backend is
configured while this is on — that's the tradeoff for the better
candidates, so it defaults off and is a separate flag from `enabled`
rather than following `"chinese" in locale.languages` automatically.
