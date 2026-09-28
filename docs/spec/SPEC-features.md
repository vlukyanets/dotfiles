# Spec: `features` — the features of the schema

Status: restarted 2026-09-28. Module of the [capability map](CAPABILITY-MAP.md);
depends on `packages` and `render`.

## Objective

Every `features.<name>` in `dotfiles/defaults.toml` does what its table in
the schema says, through the engine: a check first, a change only when the
check fails, root only through `as_root`. The list starts from scratch:
features come back one at a time, each with its settings, its
dependencies and its tests. Today there is one, `packaging`.

## Structure

One module per feature, `dotfiles/features/<name>.py`, one `Feature`
subclass, its name the feature's: the runner gates it by the file name. A
nested class per platform (`Arch`, `Linux`, …) is its strategy there, with
its packages, what they replace and the features it requires; a feature
without one for a platform does not run there.

A file a feature writes outside `$HOME` is a Jinja2 template under
`system/`, at its path from `/`: `system/etc/pacman.conf.d/options.conf.j2`
for `/etc/pacman.conf.d/options.conf`. `render.template(dst, **context)`
renders it; the feature writes the text with `ensure_file`. The context is
what the feature passes, not the whole config.

## `packaging` — pacman and makepkg

```toml
[features.packaging]
enabled = true

[features.packaging.pacman]
parallel_downloads = 5
multilib           = true
flags              = ["Color", "VerbosePkgLists"]

[features.packaging.makepkg]
jobs     = "50%"
packager = "Ann Lee <ann@lee.org>"
options  = ["ccache", "!debug"]
```

Arch only, no packages, no requirements. Only drop-ins are written; the
main files keep everything the drop-ins do not set. A setting left at its
default writes nothing, so the main file's own value stays.

- `/etc/pacman.conf.d/options.conf` (`root:root` 644), from its template:
  `ParallelDownloads = N` when `parallel_downloads > 0`, then one line per
  name in `flags`, the options pacman takes without a value (`Color`,
  `VerbosePkgLists`, `CheckSpace`, `ILoveCandy`, …): present means on.
- pacman does not read `/etc/pacman.conf.d` on its own, so `pacman.conf`
  gets `Include = /etc/pacman.conf.d/options.conf`, before its first
  repository section: options after it would be ignored. That line and
  multilib's are the only edits to `pacman.conf`.
- `multilib = true` enables the repository itself, whatever `pacman.conf`
  says: `/etc/pacman.conf.d/multilib.conf` (`[multilib]`, `Include =
  /etc/pacman.d/mirrorlist`) and its `Include` line appended to
  `pacman.conf`. While `/var/lib/pacman/sync/multilib.db` does not exist:
  `Pacman.upgrade()` (`pacman -Syu --noconfirm`, as root, retried); a full upgrade, not `-Sy`,
  which followed by `-S` is a partial upgrade. An active `[multilib]` in
  `pacman.conf` itself fails the feature before any change (`comment that
  section out`): pacman refuses a second section of the same repository
  (`could not register 'multilib' database`). With `multilib = false`
  that section is `pacman.conf`'s own business.
- `/etc/makepkg.conf.d/dotfiles.conf` (`root:root` 644), which makepkg
  reads after `makepkg.conf`: `MAKEFLAGS="-jN"` when `jobs` is set,
  `PACKAGER="…"` when `packager` is, `OPTIONS+=(…)` when `options` is not
  empty.
- `jobs` is an integer, the threads, or a string `"NN%"`, that share of
  `os.cpu_count()` at the apply, at least 1; `0` leaves `makepkg.conf`'s.

The config checks what a type cannot (`config.RULES`), so `dotfiles check`
names the key: `parallel_downloads` and an integer `jobs` not below 0, a
string `jobs` a positive percent, `packager` empty or `Name <email>`,
`flags` from pacman's list of valueless options.

## Project Structure

```
dotfiles/features/packaging.py            the feature
system/etc/pacman.conf.d/options.conf.j2  its templates
system/etc/pacman.conf.d/multilib.conf.j2
system/etc/makepkg.conf.d/dotfiles.conf.j2
dotfiles/defaults.toml                    features.packaging and its settings
dotfiles/config.py                        EITHER (jobs: integer or string), RULES
tests/test_features.py                    each feature against a fake machine
```

## Testing Strategy

- Every command faked, root's files written under a temp sysroot
  (`conftest.machine`).
- Defaults: both drop-ins hold only their header, the `Include` lands
  before `[core]`, no multilib, no pacman command; a second apply prints
  nothing.
- Every setting set: the lines in order; `"50%"` of a patched
  `cpu_count`; a percent never below one thread.
- multilib: the drop-in, its `Include` at the end, `-Syu` once, nothing
  once `multilib.db` exists; an active `[multilib]` of `pacman.conf` fails
  before any change, a commented-out one does not, and neither matters
  with multilib off.
- `test_real_features_are_consistent`: every schema feature has a module
  and every module a schema table.

## Boundaries

- **Always:** templates for every file written; check before mutating;
  root only through `as_root`.
- **Ask first:** editing `pacman.conf` or `makepkg.conf` beyond the
  `Include` lines; an automatic `-Syu` outside enabling multilib.
- **Never:** `pacman -Sy` without `-u`.

## Decisions

1. **`packaging` is an ordinary feature**, not the platform's setup. A
   feature that needs it (multilib for lib32 packages) will say so in
   `requires()` once the dependency rework lands.
2. **A default writes nothing**: `0`, `""`, `[]` and `false` leave the
   main file's value, so a host sets only what it wants to change.
3. **Valueless options are a list** (`flags`), since TOML has no key
   without a value and `false` could not turn one off anyway.
4. **`jobs` has no shell expressions** (`"$(nproc)"`): a number or a
   percent, resolved at the apply.
