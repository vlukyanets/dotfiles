# Layout reference

- `.hosts.toml` — per-host config, keyed by hostname (data, not templates)
- `.chezmoi.toml.tmpl` — turns a host's entry into template variables, defaults included
- `.chezmoiignore.tmpl` — per-host file exclusions
- `dot_*` / `private_dot_*` — become `~/.*` on `apply` (chezmoi's naming
  convention: `dot_` → `.`, `private_` → mode `0600`)
- `.chezmoiscripts/run_once_*` — one-time setup scripts (package installs,
  etc.); `run_once_` means chezmoi runs it once per content hash, re-running
  automatically whenever the script's content changes
