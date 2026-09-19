# CI

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml) ("CI Dotfiles")
runs on every push to `master` and on every pull request. Nothing in it
is GitHub-specific beyond the matrix: each job is a script under
[`ci/`](../ci), runnable here too. The jobs run in an `archlinux:latest`
container, so chezmoi, shellcheck, luacheck and lychee are the same
pacman packages a host has — not Ubuntu's versions, which lag (a
shellcheck one release behind flagged a line the current one doesn't).
Actions are pinned by commit hash, with the tag in a comment.

## What it proves

Nothing in this repo runs until `chezmoi apply` on a real machine, so
the checks are about the step before that — does the source *render*,
for every machine it's meant for, and is what it renders sane.

1. **Every registered host renders.** [`ci/hosts.sh`](../ci/hosts.sh)
   lists the top-level tables of `.hosts.toml`; the workflow fans out
   over them, so a host is checked from the commit that adds it, and a
   change made for one machine that breaks another's config fails there.
   For each host, [`ci/render.sh`](../ci/render.sh) does what `chezmoi
   init && chezmoi apply` would, with the hostname faked through
   `--override-data` (no need to be on the machine): renders
   `.chezmoi.toml.tmpl` into the host's data, executes every template in
   the tree against it, lists the managed targets and runs `chezmoi apply
   --dry-run` into an empty directory — the full apply plan, nothing
   written, no script run. It fails on a template error, on a `fail`
   call from a template (an `ide.vscode.profiles` name that isn't in
   `profiles.json`, say), and on a target outside `$HOME`'s dotfiles —
   which is how `README.md`, `LICENSE` and `CLAUDE.md` turned out to be
   landing in `$HOME` on every apply until `.chezmoiignore.tmpl` listed
   them.
2. **Variants no real host has switched on.** The same render with
   settings flipped on top of the host's: `headless` (no desktop,
   greeter, NVIDIA, fcitx5 or VS Code — a server) and `zsh` (the
   `.zshrc`/oh-my-zsh side, which no registered host currently enables).
   `_empty` is a host registered with an empty table — the state a new
   machine starts in, every default in play, which is what
   [adding a machine](adding-a-machine.md) says is enough.
3. **Rendered scripts lint.** [`ci/check-scripts.sh`](../ci/check-scripts.sh)
   runs `sh -n` and shellcheck over every rendered `run_once_before_*`
   script from every host and variant, and luacheck over the rendered
   `init.lua`. Templates can't be linted as templates; the rendered
   output is the real script, so that's what gets checked.
4. **Data and docs.** [`ci/check-data.sh`](../ci/check-data.sh) parses
   `.hosts.toml` and every JSON file on their own, and checks that
   `.chezmoiscripts` is numbered `01..N` without gaps and that
   [`docs/host-config/README.md`](host-config/README.md)'s numbered list
   has one entry per script — the numbers are the only link between the
   two. [lychee](https://github.com/lycheeverse/lychee) then follows
   every relative link and `#anchor` between the Markdown files, offline
   — the binary from pacman, the same command as below.

Not in it: a real `chezmoi apply`. The scripts talk to `pacman`,
`systemctl`, AUR builds and hardware; in a container half of them would
have to be special-cased, and the ones that matter most (NVIDIA, the
greeter, networking) can't run there anyway. The dry run gets everything
short of executing them.

## Running it locally

```sh
ci/render.sh hyper-lin            # or any host in .hosts.toml
ci/render.sh hyper-lin headless   # a variant; `zsh` is the other
ci/render.sh _empty               # a fresh, empty host entry
ci/check-scripts.sh               # over whatever render.sh produced
ci/check-data.sh
lychee --offline --include-fragments --exclude-path ci/out '**/*.md'
```

Output goes under `ci/out/<host>[-<variant>]/` (gitignored, and in
`.chezmoiignore.tmpl` along with the rest of `ci/`): the host's rendered
`chezmoi.toml`, every script under `scripts/`, `init.lua`, the `managed`
list. `check-scripts.sh` skips shellcheck or luacheck when they aren't
installed and says so; on hyper-lin they're in `cli_tools.enabled`
together with lychee, so the whole set runs before a push.
