# Spec: `features` — the features of the schema

Module of the [capability map](CAPABILITY-MAP.md);
depends on `packages` and `render`.

## Objective

Every `features.<name>` in `dotfiles/defaults.toml` does what its table in
the schema says, through the engine: a check first, a change only when the
check fails, root only through `shell.as_root`. Today there are
`packaging`, `reflector` and `paru`.

## Structure

Platforms share no feature code. Each has its own directory,
`dotfiles/platforms/<name>/features/`, one module per feature, and in it one
`Feature` subclass named after the module (`packaging` → `Packaging`,
`nvidia_driver` → `NvidiaDriver`): the runner finds it by that name
(`discovery.named`) and gates it by the file name. A platform runs its own
module of a name, else its base's: `linux/features/` holds what every Linux
does the same, and is the only code two platforms share. A feature with no
module on a platform, nor on Linux, does not run there. A module whose name
starts with `_` is a helper of that platform's features, not one itself.

A feature is built with `(settings, system)`, `settings` being
`features.<name>` and `system` the platform (`ArchLinuxOs`), and reaches its
package manager and the machine through it (`self.system.files.ensure(...)`,
`self.system.manager`). It declares `packages()`, `replaces()` and
`requires()`, each `[]` by default, and does the rest in `apply()`.

The schema is one for every platform: `features.<name>` in
`dotfiles/defaults.toml`, and the checks the types cannot make are the
`rules` and `types` of that name's classes, gathered from every platform
by `feature.checks()` and passed to `config` by the entry points.

A file a feature writes outside `$HOME` is a Jinja2 template under
`system/`, at its path from `/`: `system/etc/pacman.conf.d/options.conf.j2`
for `/etc/pacman.conf.d/options.conf`. `render.template(dst, **context)`
renders it; the feature writes the text with `files.ensure`. The context is
what the feature passes, not the whole config.

## `packaging` — pacman and makepkg

```toml
[features.packaging.pacman]
parallel_downloads = 5
multilib           = true
flags              = ["Color", "VerbosePkgLists"]

[features.packaging.makepkg]
jobs     = "50%"
packager = "Ann Lee <ann@lee.org>"
options  = ["ccache", "!debug"]
```

Arch only (`platforms/arch/features/packaging.py`), no packages, no
requirements: `apply()` does it all. It has no `enabled`: every Arch
machine has pacman, so it always runs there. Its keys have no default:
the schema holds only the empty `pacman` and `makepkg` tables, and
`Packaging.types` gives each key its type, so a key is in the resolved
config only when a host or profile sets it. Only drop-ins are written, and
only for what is set: with nothing set the feature touches nothing, and
the main files keep everything the drop-ins do not set.

- `/etc/pacman.conf.d/options.conf` (`root:root` 644) and its `Include`,
  when `parallel_downloads` or `flags` is set, from its template:
  `ParallelDownloads = N` when `parallel_downloads` is set, then one line per
  name in `flags`, the options pacman takes without a value (`Color`,
  `VerbosePkgLists`, `CheckSpace`, `ILoveCandy`, …): present means on.
- pacman does not read `/etc/pacman.conf.d` on its own, so `pacman.conf`
  gets `Include = /etc/pacman.conf.d/options.conf`, before its first
  repository section: options after it would be ignored. That line and
  multilib's are the only edits to `pacman.conf`.
- `multilib` not set: its drop-in, its `Include` and `pacman.conf`'s own
  `[multilib]` are left as they are. Set, `/etc/pacman.conf.d/multilib.conf`
  (`root:root` 644) and its `Include` line appended to `pacman.conf` are
  written either way, so the setting follows `multilib` both ways: `true` puts `[multilib]` (`Include =
  /etc/pacman.d/mirrorlist`) in it, whatever `pacman.conf` says; `false`
  leaves it only its header, which takes the repository out again after a
  `true`. While multilib is on and `/var/lib/pacman/sync/multilib.db` does not exist:
  `Pacman.upgrade()` (`pacman -Syuw` as root, retried, then `-Su`); a full upgrade, not `-Sy`,
  which followed by `-S` is a partial upgrade. An active `[multilib]` in
  `pacman.conf` itself fails the feature before any change (`comment that
  section out`): pacman refuses a second section of the same repository
  (`could not register 'multilib' database`). With `multilib = false`
  that section is `pacman.conf`'s own business.
- `/etc/makepkg.conf.d/dotfiles.conf` (`root:root` 644), when any `makepkg`
  key is set; makepkg reads it after `makepkg.conf`: `MAKEFLAGS="-jN"` when `jobs` is set,
  `PACKAGER="…"` when `packager` is, `OPTIONS+=(…)` when `options` is not
  empty.
- `jobs` is an integer, the threads, or a string `"NN%"`, that share of
  `os.cpu_count()` at the apply, at least 1; not set leaves `makepkg.conf`'s.

The config checks what a type cannot (`Packaging.rules`), so `dotfiles check`
names the key: `parallel_downloads` and an integer `jobs` at least 1, a
string `jobs` a positive percent, `packager` `Name <email>`,
`flags` from pacman's list of valueless options.

## `reflector` — the mirrorlist

```toml
[features.reflector]
enabled            = true
country            = ["Germany", "PL"]  # empty: every country
protocol           = "https"
latest             = 20
sort               = "rate"
age                = 12                 # hours
completion_percent = 100
download_timeout   = 5                  # seconds
on_calendar        = "weekly"
on_boot_sec        = "15min"
```

Arch only (`platforms/arch/features/reflector.py`), off by default, on in
`profiles/base.toml`. Its package is `reflector`; then `apply()`:

- `/etc/xdg/reflector/reflector.conf` (`root:root` 644), the arguments
  `reflector.service` reads, one per line: `--save /etc/pacman.d/mirrorlist`,
  `--country "A,B"` only when `country` is not empty (quoted: the file is
  split like a shell line, and names have spaces), then `--protocol`,
  `--latest`, `--sort`, `--age`, `--completion-percent`, `--download-timeout`.
  Every key has a default, since the file is ours whole.
- `/etc/systemd/system/reflector.timer.d/override.conf` (`root:root` 644):
  `OnCalendar` and `OnBootSec`, each emptied first, since a timer adds up
  every one it is given; `systemctl daemon-reload` when it changed.
- `ensure_service("reflector.timer")`.
- Any of these changed: `systemctl start reflector.service` as root, so the
  next install downloads from the new mirrors. Its failure is a notice, not
  an error: the old mirrorlist stays and the timer tries again.

`Reflector.rules`: `protocol` and `sort` from reflector's names, `latest`,
`age` and `download_timeout` at least 1, `completion_percent` 0 to 100,
`on_calendar` and `on_boot_sec` not empty.

## `paru` — the AUR helper

```toml
[features.paru]
enabled = true
```

Arch only (`platforms/arch/features/paru.py`), off by default, on in
`profiles/base.toml`. No settings. It builds paru from the AUR and installs
it, two steps apart: makepkg builds as the user (it refuses root), pacman
installs as root; makepkg never calls sudo itself.

- Packages: `base-devel`, `git`, and `rustup` for cargo, replacing `rust`,
  which conflicts with it. Requires `packaging`, so makepkg builds with its
  `MAKEFLAGS` and `OPTIONS`.
- `rustup default stable`, retried, while rustup has no default toolchain:
  cargo runs only with one.
- `paru --version` runs: nothing more. That is the check, not the
  package: a paru left behind by a libalpm bump is installed and does not
  run, so it is built again.
- The build, as the user, in a temp dir under `~/.cache/dotfiles` (not
  `/tmp`, where a tmpfs may be too small for cargo): `git clone --depth 1`
  of `https://aur.archlinux.org/paru.git`, then `makepkg --noconfirm
  --cleanbuild`, each retried; no `-s`, since `packages()` brought the
  dependencies. The files are those of `makepkg --packagelist` that exist
  (paru-debug only with the debug option); none fails the feature.
- The install, as root: `pacman -U --needed --noconfirm` of those files.
- As root itself the feature fails at once: makepkg would refuse.
- Dry run: the checks only, and `paru built and installed` reported.

## Project Structure

```
dotfiles/platforms/arch/features/packaging.py  Packaging: rules, types, drop-ins, multilib
system/etc/pacman.conf.d/options.conf.j2       its templates
system/etc/pacman.conf.d/multilib.conf.j2
system/etc/makepkg.conf.d/dotfiles.conf.j2
dotfiles/platforms/arch/features/reflector.py Reflector: rules, config, timer, refresh
system/etc/xdg/reflector/reflector.conf.j2    its templates
system/etc/systemd/system/reflector.timer.d/override.conf.j2
dotfiles/platforms/arch/features/paru.py      Paru: rustup's toolchain, build, install
dotfiles/defaults.toml                         every feature and its settings
tests/test_features.py                         each feature against a fake machine
```

## Testing Strategy

- Every command faked, root's files written under a temp sysroot
  (`conftest.machine`).
- Defaults: every drop-in holds only its header, the options `Include`
  lands before `[core]`, multilib's at the end, no pacman command; a
  second apply prints nothing.
- Every setting set: the lines in order; `"50%"` of a patched
  `cpu_count`; a percent never below one thread.
- multilib: the drop-in, its `Include` at the end, `-Syuw` and `-Su` once, nothing
  once `multilib.db` exists; off again, the drop-in back to its header; an active `[multilib]` of `pacman.conf` fails
  before any change, a commented-out one does not, and neither matters
  with multilib off.
- reflector: every argument in order, the country quoted; `daemon-reload`,
  the timer enabled and one refresh on the first apply, nothing on the
  second; a changed setting refreshes without a reload; a failed refresh
  is a notice.
- paru: the toolchain, clone and `makepkg` without sudo, then `sudo pacman
  -U` of the built file only; nothing when `paru --version` runs; a dry run
  only checks; as root it fails.
- `test_real_features_are_consistent`: every schema feature has a module
  and every module a schema table; paru alone requires another (packaging).

## Boundaries

- **Always:** templates for every file written; check before mutating;
  root only through `shell.as_root`.
- **Ask first:** editing `pacman.conf` or `makepkg.conf` beyond the
  `Include` lines; an automatic `-Syu` outside enabling multilib.
- **Never:** `pacman -Sy` without `-u`.

## Decisions

1. **`packaging` is an ordinary feature**, not the platform's setup. A
   feature that needs it (multilib for lib32 packages) will say so in
   `requires()` once the dependency rework lands.
2. **A default writes nothing**: `0`, `""`, `[]` and `false` leave the
   main file's value, so a host sets only what it wants to change. multilib
   is the exception: `false` empties its drop-in, since the repository
   there is ours.
3. **Valueless options are a list** (`flags`), since TOML has no key
   without a value and `false` could not turn one off anyway.
4. **`jobs` has no shell expressions** (`"$(nproc)"`): a number or a
   percent, resolved at the apply.
