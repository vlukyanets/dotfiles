# System files

[`.chezmoiscripts/run_once_before_15-configure-system-files.sh.tmpl`](../../.chezmoiscripts/run_once_before_15-configure-system-files.sh.tmpl)
copies static files that are identical on every host from
[`system/`](../../system) (relative to this repo's source directory) onto
the real filesystem, root-owned. It's unconditional — no host-config flag
gates it — since everything it deploys is meant to apply everywhere.

This is a different mechanism from the heredocs the rest of this repo
writes inline (see [SSH hardening](ssh-hardening.md), [zram](zram.md),
[Transparent hugepages](thp.md), or [Greeter](greeter.md)): those write
per-host-templated content, so a heredoc with `{{ .field }}` substitutions
makes sense. `system/` is for files with nothing to template — currently
just `system/etc/modprobe.d/nobeep.conf` (`blacklist pcspkr`, silencing the
PC speaker beep).

`system` is listed in [`.chezmoiignore.tmpl`](../../.chezmoiignore.tmpl) so
chezmoi never tries to deploy that directory under `$HOME` the normal way
— it's only ever read explicitly, via `{{ .chezmoi.sourceDir }}/system/...`
inside this one script.

## Adding a new file

1. Drop the file under `system/<path>`, e.g. `system/etc/foo.conf`.
2. Add one call: `install_system_file <path> <dest> <owner> <mode>`, e.g.
   `install_system_file etc/foo.conf /etc/foo.conf root:root 644`.
3. Add a matching tracking comment at the bottom of the script:
   `# chezmoi:tracking <path>={{ include "system/<path>" | sha256sum }}`.

That comment isn't a real chezmoi directive — chezmoi doesn't parse it. It
works because `run_once_*` scripts are re-run whenever their own *rendered*
content changes, and embedding the source file's hash means any edit to
`system/<path>` changes this script's rendered output too, even though
nothing else in the script itself changed. Skipping step 3 means an edit to
the file under `system/` silently never reaches an already-provisioned
host.
