# Pacman & makepkg

[`.chezmoiscripts/run_once_before_00-configure-pacman.sh.tmpl`](../../.chezmoiscripts/run_once_before_00-configure-pacman.sh.tmpl)
wires up `/etc/pacman.conf.d/options.conf` (`ParallelDownloads`), optionally
enables the `[multilib]` repo via `/etc/pacman.conf.d/multilib.conf`, and
writes `/etc/makepkg.conf.d/dotfiles.conf` (`MAKEFLAGS`), all driven by
`.hosts.toml`:

- `pkg_mgmt.pacman.parallel_downloads` is a fixed integer only —
  `pacman.conf` isn't shell, so there's no later point where a percentage or
  shell expression could still be evaluated. `chezmoi init` fails loudly
  (rather than silently misbehaving) if given one.
- `pkg_mgmt.pacman.multilib` (default `false`) gates the `[multilib]` repo
  entirely — hosts that leave it unset never get `pacman.conf` touched for
  it. Needed for any 32-bit package, `lib32-nvidia-utils` ([NVIDIA](nvidia.md))
  included; if a host already enables `[multilib]` directly in
  `/etc/pacman.conf` itself (rather than through this repo's
  `Include=`), the script notices and leaves it alone either way.
- `pkg_mgmt.makepkg.jobs` accepts a plain integer ("4"), a percentage of CPU
  count ("20%", floored and clamped up to a minimum of 1 whenever the
  percentage is > 0%, resolved by `resolve_parallel()` in the script), or a
  raw shell expression like `"$(nproc)"` (the default) — which, unlike the
  other two forms, is written through unresolved and evaluated fresh at
  every build rather than once at apply time, since `makepkg.conf` is
  sourced as shell.

`pkg_mgmt.reflector.save` is also read by this script's multilib `Include=`
line, so it always agrees with [reflector](reflector.md) on which mirrorlist
file is in play — change it once, in `.hosts.toml`, not in either script.
