# rbw

[`dot_config/rbw/config.json.tmpl`](../../../dot_config/rbw/config.json.tmpl)
configures [rbw](https://github.com/doy/rbw), an unofficial Bitwarden CLI
client. Ported from the old `__dotfiles` repo's values, templated only on
`email` (`.git.user.email` — the same value already used for
[`~/.gitconfig`](../../../dot_gitconfig.tmpl)), since that's the one field
here that's genuinely host/user-specific:

- `lock_timeout` (900s) / `sync_interval` (3600s) — how long a session
  stays unlocked, and how often rbw refreshes its local vault cache.
- `pinentry` set to `pinentry-tty` — rbw shells out to whatever this names
  for the master-password prompt; `pinentry-tty` works from a plain
  terminal without a display server dependency, unlike the GTK/Qt
  pinentry frontends.
- `base_url`/`identity_url`/`ui_url`/`notifications_url`/`client_cert_path`
  all `null` — rbw talks to upstream Bitwarden's own servers rather than
  a self-hosted Vaultwarden instance; set these if that ever changes.

`.chezmoiignore.tmpl` skips `~/.config/rbw` entirely on a host that leaves
`password_managers.rbw.enabled` unset — see
[Password managers](../password-managers.md).

`rbw` needs a working pinentry program on `$PATH` at runtime —
`password_managers.rbw.packages` should list `pinentry` (the Arch package
providing `pinentry-tty` among its other frontends) alongside `rbw`
itself, the same "list every package this entry actually needs" shape as
[`terminals.<name>.packages`](../terminals.md).
