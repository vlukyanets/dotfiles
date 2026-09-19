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

Keybindings aren't managed — this is the one `settings.json` file plus
the profiles below, added on demand rather than as a placeholder for the
rest of VS Code's config surface. Extensions are, per profile — the
Default profile only holds the ones applied to all of them.

## Profiles

[`.chezmoiscripts/run_once_before_27-configure-vscode-profiles.sh.tmpl`](../../../.chezmoiscripts/run_once_before_27-configure-vscode-profiles.sh.tmpl)
sets up VS Code [profiles](https://code.visualstudio.com/docs/configure/profiles)
— one per stack, so a project opens with only its own language tooling
loaded and nothing else's language servers idling in the background.
The profiles themselves are defined in
[`dot_config/Code/User/profiles.json`](../../../dot_config/Code/User/profiles.json),
next to `settings.json`, not in `.hosts.toml`: extension lists and
nested settings are JSON-shaped things, and this keeps them in the one
place VS Code's config already lives. The file becomes
`~/.config/Code/User/profiles.json` like everything else in the
directory (VS Code ignores it — it's read by the script, from the
chezmoi source). Its shape:

```json
{
    "extensions": ["editorconfig.editorconfig", "ms-vscode-remote.vscode-remote-extensionpack", "..."],
    "profiles": {
        ".NET":   { "extensions": ["ms-dotnettools.csharp"] },
        "Python": {
            "extensions": ["ms-python.python", "ms-python.vscode-pylance", "ms-python.debugpy", "charliermarsh.ruff"],
            "settings": { "[python]": { "editor.defaultFormatter": "charliermarsh.ruff" } }
        },
        "Rust":    { "...": "..." },
        "Node.JS": { "...": "..." }
    }
}
```

- The top-level `extensions` list is the set every profile gets: it's
  installed into the Default profile once and marked the way the UI's
  *Apply Extension to all Profiles* does, so every profile — the ones
  here and any created later from the UI — sees it without a copy of
  its own. Editor-wide things go here — EditorConfig, the spell checker, TOML/YAML support,
  the container tools, Remote Repositories, and the Remote Development
  pack — an extension pack that pulls in Remote-SSH (and its config
  editor), Tunnels, Remote Explorer, Dev Containers and WSL as
  dependencies, so none of those are listed on their own.
- `profiles.<name>` keys are the display names exactly as VS Code shows
  them. Each has its own `extensions` (marketplace IDs, `publisher.name`
  as `code --list-extensions` prints them) and optional `settings` —
  overrides on top of the base `settings.json`, in VS Code's own settings
  shape, nested `[language]` blocks included. The ones here mostly pin a
  formatter per language so the base `formatOnSave` has something to
  run; without one VS Code just prompts to pick.

The host side is one optional list on the entry, `ide.vscode.profiles`
— which of the file's profiles to set up on that host, by name. Left
out (as on hyper-lin) it means all of them; a name that isn't in the
file fails `chezmoi apply` at template time rather than silently doing
nothing:

```toml
[hyper-lin.ide.vscode]
enabled = true
source = "aur"
packages = ["visual-studio-code-bin"]
# profiles = ["Python", "Rust"]   # subset; unset = every profile in profiles.json
```

The script skips itself entirely unless `ide.vscode.enabled` is true, so
the [IDE](../ide.md) script's install has already run by the time it
needs `code` on `PATH`.

### Why a script, and what it touches

The `code` CLI can install extensions *into* a profile (`code --profile
Python --install-extension ms-python.python`) but can't create one — a
profile that isn't registered yet just gets `Profile 'Python' not
found.`; creation is a UI action. VS Code keeps the registry in
`~/.config/Code/User/globalStorage/storage.json`, under
`userDataProfiles`, as `{"location": "<dir under User/profiles/>",
"name": "..."}` entries. So the script, in order:

1. **Registers** every listed profile that isn't in `storage.json` yet,
   with `jq`, leaving every other key of the file (window state,
   workspace↔profile associations) and every profile *not* listed here
   untouched. New entries get a slug of the name as their `location`
   (`Python` → `python`, `Node.JS` → `node-js`, `.NET` → `net`), so
   `~/.config/Code/User/profiles/python/` is findable; a profile of the
   same name that already exists — created from the UI, with VS Code's
   random hex id — is adopted as-is, since moving its directory would
   orphan its data. Each entry also gets `useDefaultFlags` set so the
   profile shares the Default profile's keybindings, snippets and tasks
   (and its `settings.json` too, when the profile has no `settings` of
   its own); extensions are never shared — that's the point.
2. **Writes `settings.json`** for a profile that has `settings`: the
   Default profile's [`settings.json`](../../../dot_config/Code/User/settings.json)
   (read from the chezmoi *source*, like `profiles.json` — this is a
   `before` script and the targets may not exist yet on a fresh host)
   with the overrides merged on top, so a profile only ever adds to the
   shared defaults.
3. **Installs extensions**: the shared list into the Default profile
   (`code --install-extension …`, no `--profile`), then one `code
   --profile <name> --install-extension …` per profile with its own
   list. Already-installed ones are reported and skipped. The
   marketplace returns the odd 503 and `code` has no download timeout
   to raise, so each profile's install gets five attempts with a
   growing pause (30s, 60s, … — five minutes of waiting at most), and a
   profile that still fails doesn't stop the ones after it — the script
   finishes the rest, then exits 1 naming the failed profiles, which
   leaves it un-recorded for `run_once_` so the next `chezmoi apply`
   retries (a typo'd ID fails the same way, every time, which is the
   wanted behaviour). Nothing is ever uninstalled: dropping an ID from
   the list leaves it in place until removed from the UI.
4. **Applies the shared list to all profiles** — done right after the
   Default install, before the per-profile ones. VS Code has no CLI for
   the UI's *Apply Extension to all Profiles*; what the toggle does is
   set `metadata.isApplicationScoped` on the extension's entry in the
   Default profile's registry, `~/.vscode/extensions/extensions.json`,
   after which every profile sees it (and `--profile X
   --install-extension` reports it as already installed). The script
   sets that flag with `jq` on each shared ID — and, unlike the UI, on
   an extension pack's members too (walked through each `package.json`'s
   `extensionPack`), so a profile never has the Remote Development pack
   without Remote-SSH — and strips those IDs from each profile's own
   `extensions.json`, as the toggle would, for hosts where an earlier
   version of this script had installed the shared list profile by
   profile. VS Code reads the registry on start, so with it open the
   change shows after a restart; it survives installs made from the UI
   in the meantime, which rewrite the file with its entries intact.

Step 1 is the one that needs **VS Code closed**: `storage.json` is its
in-memory state flushed to disk, and an edit made underneath a running
instance is overwritten on its next flush. The script checks Chromium's
`SingletonLock` (ignoring a stale one whose pid is gone) and, only if
there's a profile left to register, refuses with a message to close VS
Code and re-run `chezmoi apply`. Once every profile is registered, adding
extensions or changing `settings` works with VS Code open. Being a
`run_once_` script it re-runs whenever its rendered content changes —
any edit to `profiles.json`, to the host's `profiles` list, or to the
base `settings.json` it embeds — and not otherwise.

`settings.json` in a profile with overrides is rewritten on every run,
so changes made from that profile's Settings UI don't survive the next
one; put them in `profiles.json` instead. A profile without overrides has
no file of its own to clobber — it reads the Default profile's, which
chezmoi manages the same way.
