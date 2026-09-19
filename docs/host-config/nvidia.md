# NVIDIA

[`.chezmoiscripts/run_once_before_07-configure-nvidia.sh.tmpl`](../../.chezmoiscripts/run_once_before_07-configure-nvidia.sh.tmpl)
is gated behind `nvidia.enabled` (default `false`) — hosts that leave it
unset skip it entirely, including the `lspci` detection below. This is
deliberately a single on/off flag, not a driver choice: which package
actually gets installed depends on hardware and the running kernel, neither
of which `.hosts.toml` can know ahead of time, so both are detected at
apply time instead.

When enabled, it installs `pciutils` if `lspci` isn't already on `PATH`,
then looks for an NVIDIA GPU in `lspci`'s output. No match exits
immediately — enabling this on a host that turns out to have no NVIDIA GPU
(or an Intel/AMD one) is a no-op, not an error.

With a GPU found, the driver package is picked by generation, mirroring
`nvidia-utils`' own support matrix: only the current generation
(`nvidia-dkms`, for GTX 16xx/RTX-and-newer) ships in the official
repositories. Every older generation (`nvidia-580xx-dkms` for GTX 9xx/10xx,
`nvidia-470xx-dkms` for GTX 6xx/7xx, `nvidia-390xx-dkms` for GTX 4xx/5xx,
`nvidia-340xx-dkms` for GeForce 8/9/100/200/300) is AUR-only, installed via
`paru` instead of `pacman` — same as [Greeter](greeter.md)'s
`noctalia-greeter`, this requires [`pkg-mgmt.aur.enabled`](aur.md) `= true`
and fails loudly rather than silently skipping the driver if it isn't set.
An unrecognized/future GPU generation falls back to `nvidia-dkms` with a
warning rather than failing outright.

Kernel headers are matched to the *running* kernel's flavor
(`linux-zen-headers`, `linux-lts-headers`, `linux-hardened-headers`, or
plain `linux-headers`), read from `uname -r` — DKMS needs headers for the
exact kernel in use, not just whichever `linux*` package happens to be
installed.

The matching `lib32-nvidia*-utils` package is included too, but only if
[`pkg-mgmt.pacman.multilib`](pacman.md) `= true` — without `[multilib]`
enabled that package doesn't exist to install, so this only warns and
skips it (32-bit apps, e.g. games through Wine/Steam, won't get GPU
acceleration, but the driver itself still installs fine). The oldest
generation (`nvidia-340xx-dkms`) has no lib32 counterpart at all, multilib
or not.

Either way, a reboot is required before the new driver actually loads —
the script says so but doesn't reboot anything itself.
