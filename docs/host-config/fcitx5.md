# fcitx5

[`.chezmoiscripts/run_once_before_21-configure-fcitx5.sh.tmpl`](../../.chezmoiscripts/run_once_before_21-configure-fcitx5.sh.tmpl)
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
- `[Behavior/DisabledAddons]` with `0=notificationitem` — disables the
  "Notification Item" addon (`libnotificationitem.so`), the one that
  publishes a StatusNotifierItem (SNI) over D-Bus. On niri there's no
  XEmbed tray for classicui's own X11 tray window to fall back to either,
  so this is the only thing actually putting a fcitx5 icon in any
  tray/status bar — disabling it hides that icon outright. The shape
  matters: `DisabledAddons` is a list, and fcitx5 stores lists as a
  sub-group with numbered keys; a plain `DisabledAddons=notificationitem`
  line under `[Behavior]` (what this file had at first) is silently
  ignored, and `busctl --user call org.fcitx.Fcitx5 /controller
  org.fcitx.Fcitx.Controller1 GetAddonsV2` still reports the addon
  enabled. `classicui.conf`'s
  `PreferTextIcon`/`ShowLayoutNameInIcon` (see [Theme](#theme) below) are
  left as-is even though they're now moot — harmless dormant config, same
  as `cloudpinyin.conf` when [Cloud Pinyin](#cloud-pinyin) is off.

## `dot_config/fcitx5/modify_profile`

Lists which input methods fcitx5 actually has available —
`fcitx5-remote -s <name>` (used by
[`switch-layout.sh.tmpl`](desktop/niri.md#fcitx5)) can only select an
input method this profile declares. Built from
[`locale.languages`](locale.md#languages) via the same
[`.chezmoitemplates/language-codes`](../../.chezmoitemplates/language-codes)
mapping `config.kdl.tmpl` and `switch-layout.sh.tmpl` use for their own
lists, so all three stay in agreement without hand-syncing separate
per-file lists — see [niri](desktop/niri.md#keyboard-layouts-and-localelanguages)
for why that matters.

It's a `modify_` template rather than a plain one because fcitx5 rewrites
`~/.config/fcitx5/profile` on every exit, saving whichever input method
was active as `DefaultIM`. With a plain template every apply would put
the first language back — and, before that, chezmoi would stop on the
file "changed since chezmoi last wrote it" and ask what to do, every
time. A modify template gets the current file on `.chezmoi.stdin` and
produces the new one: the group and its items come from
`locale.languages` as before, but `DefaultIM` is carried over from the
existing file when it's still one of the listed input methods (a value
that isn't, or a missing file, falls back to the first language). So
when the language list hasn't changed, the output equals what fcitx5
wrote and apply has nothing to do. `conf/pinyin.conf` is rewritten by
fcitx5 the same way, but that one comes out byte-identical to the
template (the template mirrors fcitx5's own serialization — defaults
commented out, mode 0600, trailing blank line and all; see below), so it
stays a plain file.

Unlike the old `__dotfiles` version — a `run_onchange_after_*` script that
wrote `~/.config/fcitx5/profile` imperatively and force-restarted a live
fcitx5 daemon (`pkill -KILL fcitx5; fcitx5 -d`) — this is a chezmoi
dotfile like every other app config in this repo. A running session
doesn't pick up a `locale.languages` change until fcitx5 is restarted
(next login, or manually), the same caveat
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

- [`dot_config/fcitx5/conf/private_pinyin.conf.tmpl`](../../dot_config/fcitx5/conf/private_pinyin.conf.tmpl)
  — the pinyin addon's own config file, in fcitx5's own generated format
  (a `#`-commented description above each key, its default value also
  commented out unless actually set — same as what fcitx5 itself writes
  the first time it runs). Every key here is left exactly as fcitx5's own
  defaults except `CloudPinyinEnabled`, the one line templated from
  `fcitx5.cloudpinyin`. The template follows fcitx5's own rule for that
  line too: `CloudPinyinEnabled=True` uncommented when the flag is on (a
  non-default value, same as the pre-existing `FirstRun=False` line
  below it), `# CloudPinyinEnabled=False` when it's off — `False` *is*
  the default, and fcitx5 re-serializes a default back to a comment.
  That, the `private_` prefix (fcitx5 saves the file as 0600) and the
  trailing blank line are what make fcitx5's own rewrite of this file
  byte-identical to the template; an earlier version wrote the `False`
  uncommented, and every `chezmoi apply` after fcitx5 had saved its
  settings stopped on "changed since chezmoi last wrote it". Keeping
  the rest of the file intact avoids silently wiping out fcitx5's own
  reference documentation of every other pinyin setting on every
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
