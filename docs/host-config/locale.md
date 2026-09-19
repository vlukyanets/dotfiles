# Locale

[`.chezmoiscripts/run_once_before_04-configure-locale.sh.tmpl`](../../.chezmoiscripts/run_once_before_04-configure-locale.sh.tmpl)
enables each entry in `locale.locales` in `/etc/locale.gen` (uncommenting it
if it's already there commented out, appending it otherwise) and runs
`locale-gen`, then writes `/etc/locale.conf` (`LANG`) and `/etc/vconsole.conf`
(`KEYMAP`) from `locale.lang`/`locale.keymap`, and finally symlinks
`/etc/localtime` to `locale.timezone` under `/usr/share/zoneinfo/` and runs
`hwclock --systohc` to match. `locale.locales` and `locale.lang` are
independent fields — `locales` only controls what `locale-gen` compiles, so
if it doesn't already include whatever `lang` names, `LANG` ends up pointing
at a locale that was never generated.

## `languages`

`locale.languages` (default `["english"]`) isn't read by this script at
all — it's a graphical-session concern, not a console one; `locale.keymap`
above is the *console* (`vconsole.conf`) keymap and stays independent. It
names which keyboard layouts a desktop session should offer, one of
`"english"`, `"russian"`, `"ukrainian"`, `"chinese"`, and is consumed by
[niri's config](desktop/niri.md) for its xkb layout list and, on a host
with `fcitx5.enabled = true`, by [fcitx5](fcitx5.md)'s input-method
profile and niri's input-method switching. An unrecognized
entry is silently skipped rather than an error — see
[`.chezmoitemplates/language-codes`](../../.chezmoitemplates/language-codes)
for the full language → xkb/fcitx5 mapping.
