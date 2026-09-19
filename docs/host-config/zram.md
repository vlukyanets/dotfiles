# zram

[`.chezmoiscripts/run_once_before_13-configure-zram.sh.tmpl`](../../.chezmoiscripts/run_once_before_13-configure-zram.sh.tmpl)
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

## Swap tuning

`zram.swappiness` (default `0`, meaning no drop-in at all) writes
`/etc/sysctl.d/99-zram.conf` next to the device — it survives reboots,
and the script loads it at once with `sysctl -p` so it takes effect in
the running session. The kernel's swap defaults are disk numbers, and the
[Arch wiki](https://wiki.archlinux.org/title/Zram#Optimizing_swap_on_zram)
has a section on retuning them for zram; the drop-in carries three of
its four settings:

- `vm.swappiness` — the host's value. 60 tells the kernel to hang on to
  anonymous pages and drop file cache first, because swapping to disk is
  expensive; swapping to zram is a memcpy plus compression, so the wiki
  suggests going well above 60 (it names 180). hyper-lin uses 100.
- `vm.page-cluster = 0` — always, whenever the drop-in is written. It's
  the swap-in read-ahead: `2^page-cluster` pages per fault, default 3 →
  8 pages. That pays off on a disk, where the seek dominates and the
  neighbours are likely wanted soon; on zram each extra page is an extra
  decompression and 4 KiB of uncompressed memory for a page nobody asked
  for.
- `vm.watermark_scale_factor` — from `zram.watermark_scale_factor`
  (default `0`, untouched; kernel default 10, hyper-lin 125). It's the
  gap between the `low` and `high` free-memory watermarks, in units of
  0.01% of a zone: wider means kswapd wakes earlier and runs longer, so
  compressing into zram happens in the background ahead of demand rather
  than as synchronous direct reclaim inside the process that needed the
  memory. The price is that much memory held free instead of serving as
  page cache — a trade, which is why it's a field and not a constant.

The wiki's fourth, `vm.watermark_boost_factor = 0`, is left out on
purpose. The boost temporarily raises the `high` watermark when the
kernel spots fragmentation, so that kswapd frees contiguous blocks — the
defragmentation that keeps huge pages available. With
[`thp.mode = "always"`](thp.md) on the same host that's wanted, not
noise.

Re-applying is safe: the config file is overwritten with the same content
each time, and the service is restarted rather than left stale whenever it
was already running.
