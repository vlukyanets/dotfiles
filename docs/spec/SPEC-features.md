# Spec: `features` — the features of the schema

Module of the [capability map](CAPABILITY-MAP.md);
depends on `packages` and `render`.

## Objective

Every `features.<name>` in `dotfiles/defaults.toml` does what its table in
the schema says, through the engine: a check first, a change only when the
check fails, root only through `shell.as_root`. Today there are
`packaging`, `reflector`, `rustup`, `paru`, `no_beep` and `zsh`.

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

A file a feature writes is a Jinja2 template under
`system/`, at its path from `/`: `system/etc/pacman.conf.d/options.conf.j2`
for `/etc/pacman.conf.d/options.conf`. `render.template(dst, **context)`
renders it; the feature writes the text with `files.ensure`. The context is
what the feature passes, not the whole config. A dotfile's is under
`home/`, at its path from `~`: `template("~/.config/zsh/dotfiles.zsh")`
renders `home/.config/zsh/dotfiles.zsh.j2`.

## `packaging` — pacman and makepkg

```toml
[features.packaging.pacman]
contrib            = true
parallel_downloads = 5
multilib           = true
flags              = ["Color", "VerbosePkgLists"]

[features.packaging.makepkg]
jobs     = "50%"
packager = "Ann Lee <ann@lee.org>"
options  = ["ccache", "!debug"]
```

Arch only (`platforms/arch/features/packaging.py`), no requirements. It
has no `enabled`: every Arch machine has pacman, so it always runs there.
Its one package is `pacman-contrib` (paccache, checkupdates, pactree…),
while `pacman.contrib`, false by default, is true; false never removes
it. The other keys of `pacman` and `makepkg` have no default: the schema
holds only `contrib` in those tables, and
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
  written either way, so the setting follows `multilib` both ways: `true`
  puts `[multilib]` (`Include = /etc/pacman.d/mirrorlist`) in it, whatever
  `pacman.conf` says; `false` leaves it only its header, which takes the
  repository out again after a `true`. While multilib is on and
  `/var/lib/pacman/sync/multilib.db` does not exist: `Pacman.upgrade()`
  (`pacman -Syuw` as root, retried, then `-Su`); a full upgrade, not
  `-Sy`, which followed by `-S` is a partial upgrade. An active
  `[multilib]` in `pacman.conf` itself fails the feature before any change
  (`comment that section out`): pacman refuses a second section of the
  same repository (`could not register 'multilib' database`). With
  `multilib = false` that section is `pacman.conf`'s own business.
- `/etc/makepkg.conf.d/dotfiles.conf` (`root:root` 644), when any
  `makepkg` key is set; makepkg reads it after `makepkg.conf`:
  `MAKEFLAGS="-jN"` when `jobs` is set, `PACKAGER="…"` when `packager` is,
  `OPTIONS+=(…)` when `options` is not empty.
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

## `rustup` — cargo and rustc

```toml
[features.rustup]
enabled   = true
toolchain = "stable"  # beta, nightly, "1.85.0", "nightly-2026-09-01"
```

Arch only (`platforms/arch/features/rustup.py`), off by default, on in
`profiles/base.toml`. Its package is `rustup`, replacing `rust`, which
conflicts with it; then `rustup default TOOLCHAIN`, retried, which
downloads it when missing: cargo runs only with a default toolchain. Not
while it is the default already: `rustup default` prints it with the host
(`stable-x86_64-unknown-linux-gnu`), taken from `Default host:` of
`rustup show`, so a dated nightly does not pass for `nightly`. An installed
toolchain is never updated (`rustup update` is the user's), and the one it
replaces stays installed. `Rustup.rules`: `toolchain` letters, digits,
`.`, `_` and `-`.

## `paru` — the AUR helper

```toml
[features.paru]
enabled = true
```

Arch only (`platforms/arch/features/paru.py`), off by default, on in
`profiles/base.toml`. No settings, no packages: requires `packaging`, so
makepkg builds with its `MAKEFLAGS` and `OPTIONS`, and `rustup`, for
cargo.

- `paru --version` runs: nothing more. That is the check, not the
  package, which is why paru is not in `packages()`: a paru left behind
  by a libalpm bump is installed and does not run, so it is built again.
- Otherwise `manager.build(["paru"])`: built as the user, installed as
  root, like any AUR package (`SPEC-packages`), the build in
  `~/.cache/dotfiles/aur/paru`.
- Dry run: the check only, and `paru built from the AUR` reported.

## `no_beep` — no PC speaker

```toml
[features.no_beep]
enabled = true
```

Every Linux (`platforms/linux/features/no_beep.py`), off by default, on in
`profiles/base.toml`. No settings, no packages.

- `/etc/modprobe.d/nobeep.conf` (`root:root` 644): `blacklist pcspkr` and
  `blacklist snd_pcsp`, the console's beeper and ALSA's driver of the same
  speaker, so neither loads at boot.
- Those of them loaded now (`/sys/module/<name>`): `modprobe -r` as root.
  It fails while a sound server holds `snd_pcsp`: a notice that the
  speaker is silent after a reboot.

## `zsh` — zsh and oh-my-zsh

```toml
[features.zsh]
enabled = true
theme      = "powerlevel10k/powerlevel10k"   # robbyrussell by default
theme_repo = "https://github.com/romkatv/powerlevel10k.git"  # empty by default
plugins    = ["git"]
extras     = ["zsh-autosuggestions", "zsh-syntax-highlighting", "zsh-completions"]
```

Arch only (`platforms/arch/features/zsh.py`): the extras' paths are
Arch's. Off by default, on in `profiles/base.toml`. Its packages are
`zsh`, `git` and the extras; then `apply()`:

- `~/.oh-my-zsh/oh-my-zsh.sh` missing: `git clone --depth 1` of oh-my-zsh
  there as the user, retried, a directory cut off halfway removed first.
  It is never pulled: `omz update` is the user's. A dry run clones nothing.
- `theme_repo` set: cloned the same way into
  `~/.oh-my-zsh/custom/themes/<dir>`, `<dir>` the part of `theme` before
  `/` (`powerlevel10k/powerlevel10k`: the theme `powerlevel10k` of the
  clone `powerlevel10k`), while that clone has no `.git`.
- `<dir>` is `powerlevel10k`: `~/.p10k.zsh` written as it is from
  `home/.p10k.zsh` (`render.source`, no Jinja: the file `p10k configure`
  makes is full of `${#...}`), its instant prompt at the top of the
  snippet and `source ~/.p10k.zsh` after oh-my-zsh. `p10k configure` on a
  machine is undone by the next apply: its file goes into the repo.
- `~/.config/zsh/dotfiles.zsh` from `home/.config/zsh/dotfiles.zsh.j2`:
  `ZSH`, `ZSH_THEME`, `plugins`, `source $ZSH/oh-my-zsh.sh`, then the
  extras' scripts, syntax highlighting last. zsh-completions is only its
  package: its functions are in zsh's `fpath` already.
- `source ~/.config/zsh/dotfiles.zsh` in `~/.zshrc`, at the top, so the
  rest of the file stays the user's and overrides ours; a missing
  `~/.zshrc` is created with that line alone.
- A login shell other than zsh: `chsh -s /usr/bin/zsh` as root, and a
  notice to log out and back in.

`Zsh.rules`: `theme` one such name or two joined by `/`, each of
`plugins` letters, digits, `.`, `_` and `-`; `theme_repo` empty or an
`https://` URL; `extras` names from the three above.

## Project Structure

```
dotfiles/platforms/arch/features/packaging.py  Packaging: rules, types, drop-ins, multilib
system/etc/pacman.conf.d/options.conf.j2       its templates
system/etc/pacman.conf.d/multilib.conf.j2
system/etc/makepkg.conf.d/dotfiles.conf.j2
dotfiles/platforms/arch/features/reflector.py  Reflector: rules, config, timer, refresh
system/etc/xdg/reflector/reflector.conf.j2     its templates
system/etc/systemd/system/reflector.timer.d/override.conf.j2
dotfiles/platforms/arch/features/rustup.py     Rustup: rustup for rust, its default toolchain
dotfiles/platforms/arch/features/paru.py       Paru: built from the AUR while it does not run
dotfiles/platforms/linux/features/no_beep.py   NoBeep: blacklist, unload
system/etc/modprobe.d/nobeep.conf.j2           its template
dotfiles/platforms/arch/features/zsh.py        Zsh: oh-my-zsh, our part of ~/.zshrc, chsh
home/.config/zsh/dotfiles.zsh.j2               its template
home/.p10k.zsh                                 powerlevel10k's settings, copied as they are
dotfiles/defaults.toml                         every feature and its settings
tests/test_features.py                         each feature against a fake machine
tests/test_apply.py                            test_real_features_are_consistent
```

## Testing Strategy

- Every command faked, root's files written under a temp sysroot
  (`conftest.machine`).
- Nothing set: no drop-in, `pacman.conf` untouched, no command, nothing
  printed. Only `flags` set: the options drop-in alone, its `Include`
  before `[core]`; only `jobs`: `MAKEFLAGS` alone.
- `pacman.contrib`: `pacman-contrib` among the packages only when true.
- Every setting set: the lines in order; `"50%"` of a patched
  `cpu_count`; a percent never below one thread.
- multilib: the drop-in, its `Include` at the end, `-Syuw` and `-Su`,
  nothing once `multilib.db` exists or when not set; off again, the
  drop-in back to its header; an active `[multilib]` of `pacman.conf`
  fails before any change, a commented-out one does not, and neither
  matters with multilib not set.
- reflector: every argument in order, the country quoted; `daemon-reload`,
  the timer enabled and one refresh on the first apply, nothing on the
  second; a changed setting refreshes without a reload; a failed refresh
  is a notice.
- rustup: `default stable` once, nothing while it is the default; another
  toolchain switched to, a dated nightly not taken for `nightly`.
- paru: built from the AUR while `paru --version` fails, not once it runs;
  a dry run only checks.
- no_beep: the blacklist, a loaded driver unloaded once, nothing the
  second time; a driver in use is a notice.
- zsh: one clone, the snippet with the plugins chosen, the source line on
  top of an existing `~/.zshrc` or alone in a new one, `chsh` and its
  notice; nothing the second time; a dry run clones nothing and leaves a
  half clone alone. powerlevel10k: its clone, `~/.p10k.zsh` the repo's,
  the instant prompt before oh-my-zsh and the settings after; no p10k
  otherwise.
- `test_real_features_are_consistent`: every schema feature has a module
  and every module a schema table; paru alone requires others
  (packaging, rustup).

## Boundaries

- **Always:** templates for every file written; check before mutating;
  root only through `shell.as_root`.
- **Ask first:** editing `pacman.conf` or `makepkg.conf` beyond the
  `Include` lines; an automatic `-Syu` outside enabling multilib.
- **Never:** `pacman -Sy` without `-u`.

## Decisions

1. **`packaging` is an ordinary feature**, not the platform's setup. A
   feature that needs it says so in `requires()`, as `paru` does for its
   `MAKEFLAGS` and `OPTIONS`.
2. **What is not set writes nothing**: a key no host or profile sets
   leaves the main file's value, so a host sets only what it wants to
   change. multilib is the exception: `false` empties its drop-in, since
   the repository there is ours.
3. **Valueless options are a list** (`flags`), since TOML has no key
   without a value and `false` could not turn one off anyway.
4. **`jobs` has no shell expressions** (`"$(nproc)"`): a number or a
   percent, resolved at the apply.
