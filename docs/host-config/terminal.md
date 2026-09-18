# Terminal (kitty)

[`.chezmoiscripts/run_once_before_18-configure-terminal.sh.tmpl`](../../.chezmoiscripts/run_once_before_18-configure-terminal.sh.tmpl)
installs the `kitty` package when `terminal.kitty.enabled` is true (default
`false` — the script exits immediately otherwise). The same flag also
controls whether [`dot_config/kitty/kitty.conf`](../../dot_config/kitty/kitty.conf)
is written at all: `.chezmoiignore.tmpl` skips `~/.config/kitty` entirely on
a host that leaves this unset — the same "flag gates both the install and
the dotfile" shape as [shell.zsh.enabled](shell.md).

`kitty.conf` itself isn't templated — it carries no host-specific values,
just font choice, scrollback, and the Nerd Font/Noto Color Emoji
`symbol_map` ranges kitty needs to render powerline glyphs and emoji
correctly.

## Fonts

`kitty.conf` sets `font_family FiraCode Nerd Font Mono`, plus `symbol_map`
fallbacks to a "Symbols Nerd Font Mono" and to "Noto Color Emoji". Nothing
in this script installs any of those — same split as [Fonts](fonts.md):
list the packages a host needs (e.g. `["ttf-firacode-nerd",
"ttf-nerd-fonts-symbols-mono", "noto-fonts-emoji"]`) in that host's
`fonts.enabled`. Enabling `terminal.kitty` without also listing a matching
font just gets kitty running with missing/broken glyphs, not an error.
