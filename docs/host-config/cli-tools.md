# CLI tools

[`.chezmoiscripts/run_once_before_08-configure-cli-tools.sh.tmpl`](../../.chezmoiscripts/run_once_before_08-configure-cli-tools.sh.tmpl)
installs every package listed in `cli_tools.enabled` (default `[]` — the
script exits immediately on hosts that don't set it) in one `pacman -S
--needed` call. It's for standalone CLI tools, distinct from
`services.packages`: [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) checks for
`nvim`, `zoxide`, and `eza` with `command -v` before wiring up `$EDITOR`,
`zoxide init`, and the `eza`-backed `ls` aliases, but nothing installed them
until now — a host that wants that behavior needs `["neovim", "zoxide",
"eza"]` (or a subset) in `cli_tools.enabled`; a host that leaves it unset
just keeps falling back to `vim`/`nano` and plain `ls`.
