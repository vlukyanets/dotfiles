# Fonts

[`.chezmoiscripts/run_once_before_10-configure-fonts.sh.tmpl`](../../.chezmoiscripts/run_once_before_10-configure-fonts.sh.tmpl)
installs every package listed in `fonts.enabled` (default `[]` — the script
exits immediately on hosts that don't set it) in one `pacman -S --needed`
call, the same shape as [CLI tools](cli-tools.md). It exists because nothing
else installs a terminal font: `shell.zsh.oh_my_zsh.enabled` renders the
`powerlevel10k` prompt, `cli_tools.enabled` can include `eza`, and
[`terminals.kitty.enabled`](terminals.md) writes a `kitty.conf` expecting a
Nerd Font plus a symbols/emoji fallback — all three just render broken or
missing glyphs, not an error, on a host with no matching font available,
e.g. `fonts.enabled = ["ttf-meslo-nerd"]` for powerlevel10k/eza, or
`["ttf-firacode-nerd", "ttf-nerd-fonts-symbols-mono", "noto-fonts-emoji"]`
for kitty.

`fonts.nerd_font` (default `false`) is a separate plain boolean, not derived
from `enabled` — nothing here tries to pattern-match package names to guess
whether one of them is a Nerd Font. Set it to `true` once `enabled` actually
includes one; other templates read it directly, e.g.
[`dot_config/nvim/init.lua.tmpl`](../../dot_config/nvim/init.lua.tmpl)'s
`vim.g.have_nerd_font` (see [Neovim](ide/neovim.md)).
