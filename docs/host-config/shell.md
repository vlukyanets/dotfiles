# Shell

[`.chezmoiscripts/run_once_before_06-configure-shell.sh.tmpl`](../../.chezmoiscripts/run_once_before_06-configure-shell.sh.tmpl)
is gated behind `shell.zsh.enabled` (default `false`) the same way the
[AUR script](aur.md) is gated behind `pkg_mgmt.aur.enabled` — hosts that
leave it unset skip it entirely. When enabled, it installs `zsh` and (if it
isn't already the login shell) runs `chsh` to make it one. If
`shell.zsh.oh_my_zsh.enabled` is also set, it further clones oh-my-zsh, the
`powerlevel10k` theme, and the `zsh-autosuggestions`/`zsh-syntax-highlighting`
plugins into `$ZSH_CUSTOM`. Every clone is skipped if its directory already
exists, so re-running (or applying to a machine that already has these
installed by hand) is a no-op.

[`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl) skips `~/.zshrc` entirely
on any host with `shell.zsh.enabled` unset or `false` — there's no point
writing a zsh config on a host that isn't opting into zsh. On a host that
does, [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) itself further branches on
`shell.zsh.oh_my_zsh.enabled`: the oh-my-zsh/Powerlevel10k block is only
rendered into `~/.zshrc` when that's also set, matching exactly what this
script installs — a host with `shell.zsh.enabled` but not the oh-my-zsh flag
gets a plain, working `~/.zshrc` with none of that theming.
