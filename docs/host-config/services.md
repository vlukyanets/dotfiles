# Services

[`.chezmoiscripts/run_once_before_05-configure-services.sh.tmpl`](../../.chezmoiscripts/run_once_before_05-configure-services.sh.tmpl)
runs `systemctl enable --now` for each unit listed in `services.enabled`
(default `[]` — the script exits immediately without touching systemd on
hosts that don't set it). Before enabling anything, it looks up each unit
in `services.packages` (unit name → list of pacman packages that provide
it), collects the packages for every enabled unit into one deduplicated
list, and installs them in a single `pacman -S --needed` call — a unit with
no entry in `services.packages` is just enabled as-is, nothing installed.
`enable --now` is idempotent on its own, so re-running this script (or
applying on a host where a unit is already enabled and running) is always a
no-op for that unit.
