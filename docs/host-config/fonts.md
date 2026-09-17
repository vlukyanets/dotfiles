# Fonts

[`.chezmoiscripts/run_once_before_08-configure-fonts.sh.tmpl`](../../.chezmoiscripts/run_once_before_08-configure-fonts.sh.tmpl)
installs every package listed in `fonts.enabled` (default `[]` — the script
exits immediately on hosts that don't set it) in one `pacman -S --needed`
call, the same shape as [CLI tools](cli-tools.md). It exists because nothing
else installs a terminal font: `shell.zsh.oh_my_zsh.enabled` renders the
`powerlevel10k` prompt and `cli_tools.enabled` can include `eza`, but both
just render broken or missing glyphs — not an error — on a host with no
Nerd Font available, e.g. `fonts.enabled = ["ttf-meslo-nerd"]`.
