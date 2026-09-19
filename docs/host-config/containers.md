# Containers

[`.chezmoiscripts/run_once_before_11-configure-containers.sh.tmpl`](../../.chezmoiscripts/run_once_before_11-configure-containers.sh.tmpl)
is gated behind `containers.docker.enabled` (default `false`) the same way
the [AUR script](aur.md) is gated behind `pkg_mgmt.aur.enabled` — hosts that
leave it unset skip it entirely. When enabled, it installs `docker`, runs
`systemctl enable --now docker.service`, and adds the applying user to the
`docker` group if they aren't already in it. The group add is skipped (not
re-run) once the user's already a member, so re-applying is a no-op; a fresh
add still requires logging out and back in before group membership takes
effect in any existing shell, which the script prints as a reminder rather
than trying to work around.
