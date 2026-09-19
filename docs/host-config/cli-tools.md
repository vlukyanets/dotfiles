# CLI tools

[`.chezmoiscripts/run_once_before_09-configure-cli-tools.sh.tmpl`](../../.chezmoiscripts/run_once_before_09-configure-cli-tools.sh.tmpl)
installs every package listed in `cli_tools.enabled` (default `[]` — the
script exits immediately on hosts that don't set it) in one `pacman -S
--needed` call. It's for standalone CLI tools, distinct from
`services.packages`: [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) checks for
`nvim`, `zoxide`, and `eza` with `command -v` before wiring up `$EDITOR`,
`zoxide init`, and the `eza`-backed `ls` aliases, but nothing installed them
until now — a host that wants that behavior needs `["neovim", "zoxide",
"eza"]` (or a subset) in `cli_tools.enabled`; a host that leaves it unset
just keeps falling back to `vim`/`nano` and plain `ls`. `zip` and `htop`
are plain examples of a tool with no such hook — just an entry in
`cli_tools.enabled`, nothing else in the repo reacts to it. `ripgrep` and
`fd`, and `unzip` are the same as far as this script and `dot_zshrc.tmpl`
are concerned, but a host running [`ide.neovim`](ide/neovim.md) does
actually use them — Telescope shells out to `rg`/`fd`, and Mason's
installer needs `unzip` to extract most servers it downloads. That's a
plain cross-feature dependency, not anything this script enforces:
enabling `ide.neovim` without these three in `cli_tools.enabled` just
leaves Telescope's grep/find broken and some Mason installs failing, not
an error at apply time.
