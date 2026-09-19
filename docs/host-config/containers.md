# Containers

[`.chezmoiscripts/run_once_before_11-configure-containers.sh.tmpl`](../../.chezmoiscripts/run_once_before_11-configure-containers.sh.tmpl)
is gated behind `containers.docker.enabled` (default `false`) the same way
the [AUR script](aur.md) is gated behind `pkg_mgmt.aur.enabled` — hosts that
leave it unset skip it entirely. When enabled, it installs
`containers.docker.packages` (default `["docker"]`) in one `pacman -S
--needed` call, runs `systemctl enable --now docker.service`, and adds the
applying user to the `docker` group if they aren't already in it. The group add is skipped (not
re-run) once the user's already a member, so re-applying is a no-op; a fresh
add still requires logging out and back in before group membership takes
effect in any existing shell, which the script prints as a reminder rather
than trying to work around.

## `packages`

The `docker` package is only the engine and the bare `docker` CLI. The two
CLI plugins most projects assume — `docker-buildx` (what `docker build`
actually runs since BuildKit became the default builder) and
`docker-compose` (`docker compose`, the v2 plugin, not the old
Python `docker-compose` binary) — are separate Arch packages the engine
doesn't depend on, so a host that wants them lists them alongside it.
The service enable and group add don't change with the list:

```toml
[hyper-lin.containers.docker]
enabled = true
packages = ["docker", "docker-buildx", "docker-compose"]
```
