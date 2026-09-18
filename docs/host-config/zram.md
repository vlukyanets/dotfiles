# zram

[`.chezmoiscripts/run_once_before_12-configure-zram.sh.tmpl`](../../.chezmoiscripts/run_once_before_12-configure-zram.sh.tmpl)
is gated behind `zram.enabled` (default `false`) the same way the
[containers script](containers.md) is gated behind
`containers.docker.enabled` — hosts that leave it unset skip it entirely.
When enabled, it installs `zram-generator`, writes
`/etc/systemd/zram-generator.conf` with a single `[zram0]` section built
from `zram.size` (default `"min(ram / 2, 4096)"`, zram-generator's own
default — a formula string per zram-generator.conf(5), not a literal
number unless you write one), `zram.compression_algorithm` (default
`"zstd"`, this repo's own opinionated choice) and `zram.swap_priority`
(default `100`, zram-generator's own default), then runs `systemctl
daemon-reload` and starts (or restarts, if already active from a previous
apply) `systemd-zram-setup@zram0.service` so the device comes up
immediately instead of waiting for a reboot.

Re-applying is safe: the config file is overwritten with the same content
each time, and the service is restarted rather than left stale whenever it
was already running.
