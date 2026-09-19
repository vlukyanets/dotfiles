# Shell

[`.chezmoiscripts/run_once_before_08-configure-shell.sh.tmpl`](../../.chezmoiscripts/run_once_before_08-configure-shell.sh.tmpl)
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

[`dot_p10k.zsh`](../../dot_p10k.zsh), ported as-is from the old
`__dotfiles` repo (not templated — nothing in it is host-specific, just
Powerlevel10k's own prompt-segment/color choices from its configuration
wizard), is gated on `shell.zsh.oh_my_zsh.enabled` the same way — no point
shipping a Powerlevel10k config on a host that isn't installing
Powerlevel10k. `dot_zshrc.tmpl` already sources `~/.p10k.zsh` if present
(`[[ ! -f ~/.p10k.zsh ]] || source ~/.p10k.zsh`) regardless of this flag,
so a host with the file missing just falls through to `p10k configure`'s
interactive wizard on first oh-my-zsh shell start instead of failing.

`dot_zshrc.tmpl` also has one hook unrelated to oh-my-zsh: on a host with
`development.fnm.enabled` (see [Development](development.md#node-via-fnm)),
it adds `eval "$(fnm env --use-on-cd)"`, guarded by `command -v fnm` the
same way the `zoxide`/`eza` aliases already are — so a directory's
`.node-version`/`.nvmrc` switches Node versions automatically on `cd`.
It also exports `CMAKE_C_COMPILER_LAUNCHER`/`CMAKE_CXX_COMPILER_LAUNCHER=sccache`
behind `command -v sccache` — see [Development](development.md#sccache)
— and wires up `fzf --zsh` behind `command -v fzf`, like the other
[`cli_tools`](cli-tools.md) hooks.
