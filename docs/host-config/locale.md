# Locale

[`.chezmoiscripts/run_once_before_03-configure-locale.sh.tmpl`](../../.chezmoiscripts/run_once_before_03-configure-locale.sh.tmpl)
enables each entry in `locale.locales` in `/etc/locale.gen` (uncommenting it
if it's already there commented out, appending it otherwise) and runs
`locale-gen`, then writes `/etc/locale.conf` (`LANG`) and `/etc/vconsole.conf`
(`KEYMAP`) from `locale.lang`/`locale.keymap`, and finally symlinks
`/etc/localtime` to `locale.timezone` under `/usr/share/zoneinfo/` and runs
`hwclock --systohc` to match. `locale.locales` and `locale.lang` are
independent fields — `locales` only controls what `locale-gen` compiles, so
if it doesn't already include whatever `lang` names, `LANG` ends up pointing
at a locale that was never generated.
