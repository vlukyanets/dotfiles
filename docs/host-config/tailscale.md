# Tailscale

[`.chezmoiscripts/run_once_before_17-configure-tailscale.sh.tmpl`](../../.chezmoiscripts/run_once_before_17-configure-tailscale.sh.tmpl)
is gated behind `tailscale.operator` (default `false`) — hosts that leave it
unset skip it entirely. It does one thing: `tailscale set --operator=<user>`
for the applying user, so `tailscale up`/`status`/etc. work without `sudo`
afterward.

It does *not* install tailscale or enable `tailscaled.service` — that's
[Services](services.md)' job, the same generic mechanism `sshd` already uses:

```toml
[<host>.services]
enabled = ["tailscaled"]

[<host>.services.packages]
tailscaled = ["tailscale"]
```

This script only sets the operator once `tailscaled.service` is actually
active, checking with `systemctl is-active` first — if it isn't (e.g.
`tailscale.operator = true` was set without adding `tailscaled` to
`services.enabled`), it exits with an error rather than silently doing
nothing, so the misconfiguration is caught on `apply` instead of the next
time someone reaches for `tailscale` without sudo and it just fails.

`tailscale set --operator=` is safe to re-run — it just sets a preference —
so this script doesn't need its own idempotency guard.
