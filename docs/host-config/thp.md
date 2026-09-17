# Transparent hugepages (THP)

[`.chezmoiscripts/run_once_before_12-configure-thp.sh.tmpl`](../../.chezmoiscripts/run_once_before_12-configure-thp.sh.tmpl)
is gated behind `thp.enabled` (default `false`) the same way the
[zram script](zram.md) is gated behind `zram.enabled` — hosts that leave it
unset skip it entirely, and `/sys/kernel/mm/transparent_hugepage/enabled`
is left at whatever the running kernel boots with (usually `"madvise"`).

When enabled, it writes a single `w` line to `/etc/tmpfiles.d/thp.conf`
setting that sysfs file to `thp.mode` (default `"always"` — this repo's own
choice, not upstream's default), then runs `systemd-tmpfiles --create` on
that file so the change takes effect immediately instead of waiting for a
reboot. `systemd-tmpfiles-setup.service` re-applies the same `w` line on
every subsequent boot, since sysfs itself doesn't persist — the kernel
always resets `transparent_hugepage/enabled` to its compiled-in default at
boot.

`mode` accepts whatever the kernel itself accepts: `"always"`, `"madvise"`,
or `"never"`. `"always"` promotes eligible anonymous memory to hugepages
without an application having to ask for it (unlike static hugepages via
`vm.nr_hugepages`, which almost nothing outside databases/hypervisors
requests explicitly) — it can smooth out frame-time stability in
memory-hungry games and engines, at the cost of extra kernel-side
compaction work under memory pressure. Worth measuring on the actual
workload rather than assuming it helps.
