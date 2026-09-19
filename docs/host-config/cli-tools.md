# CLI tools

[`.chezmoiscripts/run_once_before_09-configure-cli-tools.sh.tmpl`](../../.chezmoiscripts/run_once_before_09-configure-cli-tools.sh.tmpl)
installs every package listed in `cli_tools.enabled` (default `[]` — the
script exits immediately on hosts that don't set it) in one `pacman -S
--needed` call. It's for standalone CLI tools, distinct from
`services.packages`: [`dot_zshrc.tmpl`](../../dot_zshrc.tmpl) checks for
`nvim`, `zoxide`, `eza`, `direnv`, and `fzf` with `command -v` before
wiring up `$EDITOR`, `zoxide init`, the `eza`-backed `ls` aliases, `direnv
hook zsh`, and `fzf --zsh` (its `C-r`/`C-t`/`Alt-c` key bindings), but
nothing installed them until now — a host that wants that behavior needs
`["neovim", "zoxide", "eza", "direnv", "fzf"]` (or a subset) in
`cli_tools.enabled`; a host that leaves it unset just keeps falling back
to `vim`/`nano`, plain `ls`, plain `C-r`, and no automatic per-directory
`.envrc` loading. `zip`, `ncdu`, and `htop` are plain examples of a tool with no
such hook — just an entry in `cli_tools.enabled`, nothing else in the repo
reacts to it. `ripgrep` and `fd`, and `unzip` are the same as far
as this script and `dot_zshrc.tmpl` are concerned, but a host running
[`ide.neovim`](ide/neovim.md) does actually use them — Telescope shells
out to `rg`/`fd`, and Mason's installer needs `unzip` to extract most
servers it downloads. That's a plain cross-feature dependency, not
anything this script enforces: enabling `ide.neovim` without these three
in `cli_tools.enabled` just leaves Telescope's grep/find broken and some
Mason installs failing, not an error at apply time. `shellcheck`,
`luacheck` and `lychee` are the same kind of entry with a different
consumer: this repo's own [CI checks](../ci.md), which skip the linters
that aren't installed — listing them on the machine you push from makes
`ci/check-scripts.sh` run the full set locally.

## Tools with a managed config

A few entries also have a config file in this repo, written only when the
tool is in `cli_tools.enabled` (each is gated in
[`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl) the same way
[`terminals.kitty`](terminals/kitty.md)'s config is on its `enabled`
flag, so a host without the tool doesn't get an orphaned dotfile):

- `tmux` — [`dot_config/tmux/tmux.conf`](../../dot_config/tmux/tmux.conf),
  plugin-free: truecolor passthrough for kitty, zero escape delay (so
  `nvim`'s mode switch doesn't lag), mouse, vi copy-mode keys, `|`/`-`
  splits and `hjkl` pane movement, windows numbered from 1, prefix moved
  from `C-b` to `C-a` (`C-a C-a` passes a literal `C-a` through).
  `prefix + r` reloads it.
- `direnv` — [`dot_config/direnv/direnv.toml`](../../dot_config/direnv/direnv.toml),
  just `hide_env_diff` (no `export +FOO ~PATH` line on every `cd`) and a
  30s `warn_timeout` instead of the 5s default, which anything creating a
  venv trips over. The shell hook itself lives in `dot_zshrc.tmpl`, as
  above.
- `git-delta` — no file of its own, but
  [`dot_gitconfig.tmpl`](../../dot_gitconfig.tmpl) checks `has "git-delta"
  .cli_tools.enabled` before setting `core.pager = delta` (plus
  `interactive.diffFilter`, `merge.conflictStyle = zdiff3`, and
  `diff.colorMoved`). Unlike the `command -v` checks in `.zshrc`, git
  config has no runtime fallback: an uninstalled pager breaks every `git
  diff` and `git log`, so the template has to gate it at apply time
  instead.
- `git-lfs` — same file, same idea: the `[filter "lfs"]` block that `git
  lfs install` would otherwise write into `~/.gitconfig` is templated in
  behind `has "git-lfs"`, so a fresh host gets it from `apply` instead of
  from remembering to run that command once.
- `tealdeer` — [`dot_config/tealdeer/config.toml`](../../dot_config/tealdeer/config.toml),
  just `auto_update = true` so `tldr` fetches its page cache on first run
  (and refreshes it monthly) instead of failing with "cache not found"
  until someone runs `tldr --update`.

## Not here: network tools

`nmap`, `tcpdump`, `dig`, wireshark and the like have their own feature,
[Network tools](network-tools.md), rather than a place in this list — they
want `desktop_only`/`groups` (wireshark's Qt frontend and capture group)
that a flat package list can't express.
