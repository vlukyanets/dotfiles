# Networking

[`.chezmoiscripts/run_once_before_05-configure-networking.sh.tmpl`](../../.chezmoiscripts/run_once_before_05-configure-networking.sh.tmpl)
is gated behind `networking.systemd_resolved.enabled` (default `false`) —
hosts that leave it unset skip it entirely. It sits right after
[Services](services.md) since it assumes NetworkManager (installed via
`services.packages` on hosts that manage it that way, or already present
otherwise) is what's actually handling the network connection — this
script only changes how DNS gets resolved on top of that, not how the
network itself comes up.

## Why systemd-resolved over dnsmasq

NetworkManager can hand DNS off to either. Both give you a local caching
resolver instead of the `dns=default` behavior (just writing whatever
servers the active connection reports straight into `/etc/resolv.conf`,
no cache, no fallback if the first one flakes). systemd-resolved was
picked over the `dns=dnsmasq` plugin because:

- It's already part of the `systemd` package — no extra package to
  install, just enabling a unit that's sitting there unused.
- `resolvectl status`/`resolvectl query` give real per-link diagnostics
  (which interface is answering which query) — `dnsmasq` has nothing
  equivalent, just its own log output.
- Proper per-link split-DNS: NetworkManager pushes each connection's DNS
  servers and search domains to resolved over D-Bus individually, so a
  VPN's private-network domains resolve through the VPN's DNS server
  specifically instead of racing against your regular connection's
  servers.
- DNSSEC and DNS-over-TLS support, if ever needed later, without
  swapping resolvers again.

## What the script does

1. `systemctl enable --now systemd-resolved.service`.
2. Symlinks `/etc/resolv.conf` → `/run/systemd/resolve/stub-resolv.conf`
   (`ln -sf`, so this happily replaces whatever NetworkManager had written
   there directly) — this is resolved's local stub listener at
   `127.0.0.53`, the one that actually does the per-link routing above,
   as opposed to `/run/systemd/resolve/resolv.conf` (upstream servers
   only, no split-DNS).
3. Writes `/etc/NetworkManager/conf.d/dns.conf`:
   ```ini
   [main]
   dns=systemd-resolved
   ```
   so NetworkManager stops writing `/etc/resolv.conf` itself and instead
   pushes per-connection DNS config to resolved.
4. Restarts `NetworkManager.service`, but only if it's already active —
   on a host where it isn't (or isn't installed yet), the `dns.conf` drop-in
   is just sitting there ready for whenever NetworkManager does start.
5. After that restart specifically, waits on `nm-online -s -q -t 30` before
   letting the rest of `chezmoi apply` continue — restarting NetworkManager
   briefly drops DNS while it reactivates every connection, and every later
   `run_once_before_*` script that needs the network (reflector, AUR, any
   `pacman -S`) would otherwise race that gap and fail with something like
   "failed to lookup address information". `nm-online -s` is the same check
   `NetworkManager-wait-online.service` itself uses to block
   `network-online.target` — it waits on NetworkManager's own activation
   state rather than polling a specific hostname, so it doesn't depend on
   some external site being reachable to decide "network's up". A 30s
   timeout just logs a warning and lets the script finish either way,
   rather than hanging `chezmoi apply` forever on a host where something
   else is actually wrong.

Every step is idempotent (`ln -sf` re-points an existing symlink instead
of erroring, `tee` rewrites the same file content, `enable --now` and the
conditional `restart` are no-ops on a host that already has this set up),
since a `run_once_before` script re-runs in full if its own content ever
changes.
