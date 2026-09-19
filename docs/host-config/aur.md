# AUR / paru

[`.chezmoiscripts/run_once_before_03-configure-aur.sh.tmpl`](../../.chezmoiscripts/run_once_before_03-configure-aur.sh.tmpl)
builds and installs [paru](https://github.com/Morganamilo/paru) from the AUR,
gated entirely behind `pkg_mgmt.aur.enabled` (default `false`) — hosts that
leave it unset skip the script without touching the network. When enabled,
it's still a no-op if `paru` is already on `PATH`, otherwise it installs
`base-devel`/`git`, clones `paru` into a scratch directory, and runs
`makepkg -si` there (unprefixed by `SUDO_CMD`, since `makepkg` refuses to run
as root — see the comment in the script).
