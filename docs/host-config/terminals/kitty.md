# kitty

[`dot_config/kitty/kitty.conf`](../../../dot_config/kitty/kitty.conf),
ported from the old `__dotfiles` repo, isn't templated — it carries no
host-specific values yet, just font choice, scrollback, and the Nerd
Font/Noto Color Emoji `symbol_map` ranges kitty needs to render powerline
glyphs and emoji correctly. `.chezmoiignore.tmpl` skips
`~/.config/kitty` entirely on a host that leaves `terminals.kitty.enabled`
unset — see [Terminals](../terminals.md).

`kitty.conf` sets `font_family FiraCode Nerd Font Mono`, plus `symbol_map`
fallbacks to a "Symbols Nerd Font Mono" and to "Noto Color Emoji". Nothing
in this script installs any of those — same split as [Fonts](../fonts.md):
list the packages a host needs (e.g. `["ttf-firacode-nerd",
"ttf-nerd-fonts-symbols-mono", "noto-fonts-emoji"]`) in that host's
`fonts.enabled`. Enabling `terminals.kitty` without also listing a matching
font just gets kitty running with missing/broken glyphs, not an error.
