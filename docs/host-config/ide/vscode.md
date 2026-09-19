# Visual Studio Code

[`dot_config/Code/User/settings.json`](../../../dot_config/Code/User/settings.json),
ported from the old `__dotfiles` repo, isn't templated — it carries no
host-specific values. `.chezmoiignore.tmpl` skips `~/.config/Code`
entirely on a host that leaves `ide.vscode.enabled` unset — see [IDE](../ide.md).

`ide.vscode.source` is `"aur"` on hyper-lin (`packages =
["visual-studio-code-bin"]`) — the official Microsoft build, not the
`code` package in the Arch repos (that one ships without Microsoft's
proprietary bits, e.g. the marketplace and some extensions won't work
against it).

## `settings.json`

Turns off every AI/telemetry feature the editor ships with
(`chat.disableAIFeatures`, `github.copilot.*`, `git.addAICoAuthor`,
`telemetry.telemetryLevel`), then a set of editor/workspace defaults
carried over as-is from `__dotfiles`: format-on-save with
`organizeImports`/`fixAll` code actions, trimmed trailing whitespace and
a final newline on save, and `files.watcherExclude`/`search.exclude`
patterns for the usual dependency/build directories across several
ecosystems (`node_modules`, `target`, `.venv`, `__pycache__`, `.gradle`,
`.idea`, etc.) so the file watcher and search don't churn through them.

Extensions and keybindings aren't managed here yet — this is only the one
`settings.json` file, added on demand as needed rather than a placeholder
for the rest of VS Code's config surface.
