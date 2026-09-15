# Reflector

[`.chezmoiscripts/run_once_before_01-configure-reflector.sh.tmpl`](../../.chezmoiscripts/run_once_before_01-configure-reflector.sh.tmpl)
installs `reflector`, writes its flags to
`/etc/xdg/reflector/reflector.conf` (the `@`-argfile `reflector.service`
already reads), drops an override at
`/etc/systemd/system/reflector.timer.d/override.conf` for the timer's
`OnCalendar`/`OnBootSec`, enables `reflector.timer`, and runs `reflector`
once immediately so the mirrorlist isn't stale until the timer's first
fire. `reflector.service` itself just runs `reflector @/etc/xdg/reflector/reflector.conf`
— every field written into that one file, `--save` included, is what both
the one-time run and every later timer-triggered run use, with nothing
timer-specific to configure beyond the `OnCalendar`/`OnBootSec` override.

`pkg_mgmt.reflector.save` is also read by [pacman](pacman.md)'s multilib
`Include=` line, so the two scripts always agree on which mirrorlist file is
in play — change it once, in `.hosts.toml`, not in either script.
