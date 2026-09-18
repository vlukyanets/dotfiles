# Conventions

**`SUDO_CMD`** — the privilege-escalation command used everywhere in this
repo (`dot_zshrc.tmpl`'s `update` alias, `.chezmoiscripts/*`). There's no
real cross-tool standard for this (checked sudo/doas, doas-sudo-shim,
topgrade — which only exposes it as a config-file option), so this repo
defines its own: every script/alias reads `${SUDO_CMD:-sudo}`, so exporting
`SUDO_CMD=doas` (in a profile sourced before `~/.zshrc`, or in the
environment a `chezmoi apply` run inherits) switches every one of them over
without touching this repo.
