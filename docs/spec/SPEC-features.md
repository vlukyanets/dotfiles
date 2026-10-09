# Spec: `features` — the features of the schema

Module of the [capability map](CAPABILITY-MAP.md);
depends on `packages` and `render`.

## Objective

Every `features.<group>.<name>` in `dotfiles/defaults.toml` does what its
table in the schema says, through the engine: a check first, a change only
when the check fails, root only through `shell.as_root`. Today there are
`packaging`; `package_tools.reflector`, `.paru` and `.pkgfile`;
`system.locale`, `.timesyncd`, `.no_beep`, `.swap`, `.zram`, `.oomd` and
`.dkms`; `shell.zsh` and `.command_not_found`; `desktop.fonts`;
`development.git` and `.rustup`; `hardware.graphics`; `gaming.steam`,
`.gamemode` and `.mangohud`.

## Structure

Platforms share no feature code. Each has its own directory,
`dotfiles/platforms/<name>/features/`, a directory per group (with an empty
`__init__.py`) and a module per feature in it, and in each module one
`Feature` subclass named after the module (`zram` → `Zram`,
`command_not_found` → `CommandNotFound`): the runner finds it by that name
(`discovery.named`) and gates it by its path, `system/zram.py` being
`system.zram`. Only `packaging` is outside a group. A group is a name, no
feature: no `enabled`, no keys of its own. A platform runs its own module
of a name, else its base's: `linux/features/` holds what every Linux does
the same, and is the only code two platforms share; a platform's module of
a name its base has too holds a subclass of the base's class, or discovery
fails. A feature with no module on a platform, nor on Linux, does not run
there. A module or group whose name starts with `_` is a helper of that
platform's features, not one itself.

A feature is built with `(settings, system)`, `settings` being
`features.<group>.<name>` and `system` the platform (`ArchLinuxOs`), and
reaches its package manager and the machine through it
(`self.system.files.ensure(...)`, `self.system.manager`). It declares
`packages()`, `replaces()` and `requires()`, each `[]` by default, and does
the rest in `apply()`. `requires()` names features by their full name
(`"shell.zsh"`) or a setting of another (`Setting("packaging.pacman.multilib",
True)`, `SPEC-engine`). A feature whose class sets `before_packages` runs
before the package install (`packaging`).

The schema is one for every platform: `features.<group>.<name>` in
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

## `package_tools.reflector` — the mirrorlist

```toml
[features.package_tools.reflector]
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

Arch only (`platforms/arch/features/package_tools/reflector.py`), off by default, on in
`profiles/arch.toml`. Its package is `reflector`; then `apply()`:

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

## `development.rustup` — cargo and rustc

```toml
[features.development.rustup]
enabled   = true
toolchain = "stable"  # beta, nightly, "1.85.0", "nightly-2026-09-01"
```

Every Linux (`platforms/linux/features/development/rustup.py`), off by default, on in
`profiles/base.toml`. Its package is `rustup`; on Arch
(`platforms/arch/features/development/rustup.py`, a subclass) it replaces `rust`,
which conflicts with it, and on Debian apt removes `rustc` and `cargo`
itself. Void's package has only `rustup-init`
(`platforms/void/features/development/rustup.py`, a subclass): while
`~/.cargo/bin/rustup` is not there, `rustup-init -y --default-toolchain
TOOLCHAIN`, retried, which installs it, the toolchain, and `~/.cargo/bin`
on the PATH of `~/.profile` and the shells' rc files; the checks after run
that rustup by its path, not yet on this process's PATH. Then `rustup default TOOLCHAIN`, retried, which
downloads it when missing: cargo runs only with a default toolchain. Not
while it is the default already: `rustup default` prints it with the host
(`stable-x86_64-unknown-linux-gnu`), taken from `Default host:` of
`rustup show`, so a dated nightly does not pass for `nightly`. An installed
toolchain is never updated (`rustup update` is the user's), and the one it
replaces stays installed. `Rustup.rules`: `toolchain` letters, digits,
`.`, `_` and `-`.

## `package_tools.paru` — the AUR helper

```toml
[features.package_tools.paru]
enabled = true
```

Arch only (`platforms/arch/features/package_tools/paru.py`), off by default, on in
`profiles/arch.toml`. No settings, no packages: requires `packaging`, so
makepkg builds with its `MAKEFLAGS` and `OPTIONS`, and
`development.rustup`, for cargo.

- `paru --version` runs: nothing more. That is the check, not the
  package, which is why paru is not in `packages()`: a paru left behind
  by a libalpm bump is installed and does not run, so it is built again.
- Otherwise `manager.build(["paru"])`: built as the user, installed as
  root, like any AUR package (`SPEC-packages`), the build in
  `~/.cache/dotfiles/aur/paru`.
- Dry run: the check only, and `paru built from the AUR` reported.

## `system.no_beep` — no PC speaker

```toml
[features.system.no_beep]
enabled = true
```

Every Linux (`platforms/linux/features/system/no_beep.py`), off by default, on in
`profiles/base.toml`. No settings, no packages.

- `/etc/modprobe.d/nobeep.conf` (`root:root` 644): `blacklist pcspkr` and
  `blacklist snd_pcsp`, the console's beeper and ALSA's driver of the same
  speaker, so neither loads at boot.
- Those of them loaded now (`/sys/module/<name>`): `modprobe -r` as root.
  It fails while a sound server holds `snd_pcsp`: a notice that the
  speaker is silent after a reboot.

## `package_tools.pkgfile` — which package has a file

```toml
[features.package_tools.pkgfile]
enabled = true
```

Arch only (`platforms/arch/features/package_tools/pkgfile.py`), off by default, on in
`profiles/arch.toml`. No settings; its package is `pkgfile`; then `apply()`:

- `ensure_service("pkgfile-update.timer")`: the database refreshed daily.
- No `*.files` in `/var/cache/pkgfile`: `pkgfile --update` as root at
  once, since until the timer's first run pkgfile finds nothing. A failed
  download is a notice; the timer tries again.

## `development.git` — the user's name and email

An example; by default `name` and `email` are empty.

```toml
[features.development.git]
enabled = true
name    = "Jane Doe"
email   = "jane@example.org"
```

Every Linux (`platforms/linux/features/development/git.py`), off by default, on in
`profiles/base.toml`; `name` and `email` are the host's. Its package is
`git`; then `apply()`:

- `~/.config/git/dotfiles.gitconfig` from
  `home/.config/git/dotfiles.gitconfig.j2`: `[user]` with `name` (quoted)
  and `email`, each only when set, none of it when neither is.
- `[include] path = dotfiles.gitconfig` at the top of
  `~/.config/git/config`, relative to it; a missing config is created
  with that line alone. The rest of the config and `~/.gitconfig`, which
  git reads after it, stay the user's and override ours.

`Git.rules`: `name` without `"`, `\` or a newline, which would need
escaping; `email` empty or one `@` between non-blanks.

## `system.locale` — locales, LANG, the console, the timezone

An example; by default `en_US.UTF-8`, the `us` keymap, no font, `UTC`.

```toml
[features.system.locale]
enabled  = true
lang     = "en_US.UTF-8"
locales  = ["en_US.UTF-8 UTF-8"]
timezone = "Europe/Kyiv"

[features.system.locale.console]
keymap   = "us"
font     = "ter-v20n"
packages = ["terminus-font"]
```

Every systemd Linux (`platforms/linux/features/system/locale.py`), off by
default, on in `profiles/base.toml` with `Europe/Kyiv`; off on the Void node, which has no
module of its own yet. Its packages are `console.packages` (Debian:
`locales`, which ships `locale-gen`); then `apply()`, the timezone first:

- `/usr/share/zoneinfo/<timezone>` missing: it fails before any change.
- Each line of `locales` uncommented in `/etc/locale.gen` (`#`, then
  blanks), or added at its end; `locale-gen` as root only when one was.
  Lines not listed are left as they are.
- `LANG=<lang>` in `/etc/locale.conf` (`root:root` 644), from
  `system/etc/locale.conf.j2`; Debian reads `/etc/default/locale`, from
  `system/etc/default/locale.j2`.
- `KEYMAP=` and, when set, `FONT=` in `/etc/vconsole.conf`, from
  `system/etc/vconsole.conf.j2`; when it changed,
  `systemd-vconsole-setup.service` restarted, its failure ignored (no
  console: a container). A font with no file in
  `/usr/share/kbd/consolefonts` is a notice. Debian writes nothing:
  console-setup reads `/etc/default/keyboard` and
  `/etc/default/console-setup`, so a keymap other than `us` or a font is
  a notice naming `dpkg-reconfigure`.
- `/etc/localtime` a symlink to the zone's file.

`Locale.rules`: `timezone` a name of word characters, `+` and `-` in
`/`-separated parts, so it stays under `/usr/share/zoneinfo`.

## `system.timesyncd` — the clock in sync

```toml
[features.system.timesyncd]
enabled = true
```

Every systemd Linux (`platforms/linux/features/system/timesyncd.py`), off by
default, on in `profiles/base.toml`, off on the Void node. No settings:
the servers are the distribution's. Part of systemd on Arch, no
packages; Debian ships it as `systemd-timesyncd`, for which apt removes
another time daemon (`chrony`, `ntpsec`). `apply()`:
`systemd-timesyncd.service` enabled and started.

## `system.swap` — a swap file on btrfs

```toml
[features.system.swap]
enabled = true
size    = "20g"
```

Every systemd Linux (`platforms/linux/features/system/swap.py`), off by default,
on in `profiles/laptop.toml`; `size` is the host's. Its package is
`btrfs-progs`; then `apply()`, which fails before any change while `size`
is empty or `/` is not btrfs (`findmnt -no FSTYPE /`):

- The subvolume `@swap` at the top of the filesystem: a swap file inside
  a snapshotted subvolume blocks its snapshots. Listing subvolumes needs
  root, so only while `swap.mount` is not active: `btrfs subvolume list /`,
  and without `@swap` the device (`findmnt -no SOURCE /`, the `[/@]`
  suffix dropped) mounted with `subvolid=5` on a temp dir, `@swap` created,
  unmounted. A dry run only says it would.
- `/etc/systemd/system/swap.mount` (`@swap` on `/swap` by the root's UUID,
  `noatime`) and `swap-swapfile.swap` (`/swap/swapfile`), from their
  templates; `daemon-reload` when either changed. Units, not fstab: a line
  of `/etc/fstab` for `/swap` or the file is a notice to remove it.
- `/swap` created, `swap.mount` enabled and started; the file created by
  `btrfs filesystem mkswapfile --size <size>` while it is not there. One
  of another size (`stat`, no root; both in whole pages) is made again:
  the `.swap` unit stopped (swapoff), the file removed and made with
  `size`, `recreated /swap/swapfile (2g -> 4g)`. A failed swapoff (its
  pages find no free RAM) leaves the file, a notice to free memory or
  reboot; the next apply tries again. Then the `.swap` unit enabled and
  started.
- No `Priority=`: the kernel gives the file a negative priority, so swap
  with a priority from 0 up (zram's) fills first, and the disk takes only
  what does not fit there.

`Swap.rules`: `size` empty or a number with one of `KMGTPE`, either case.

## `system.zram` — compressed swap in RAM

An example; by default `swappiness` and `watermark_scale_factor` are 0,
the kernel's.

```toml
[features.system.zram]
enabled                = true
size                   = "min(ram / 2, 4096)"
algorithm              = "zstd"
priority               = 100
swappiness             = 100
watermark_scale_factor = 125
```

Every systemd Linux (`platforms/linux/features/system/zram.py`), off by default,
on in `profiles/laptop.toml` and on the arch and deb nodes. Its package
is `zram-generator` (Debian: `systemd-zram-generator`); then `apply()`:

- `/etc/systemd/zram-generator.conf` from its template: `[zram0]` with
  `zram-size`, `compression-algorithm` and `swap-priority`; when it
  changed, `daemon-reload` and `systemd-zram-setup@zram0.service`
  restarted, so zram0 takes it now. The restart's stop is a swapoff of
  zram0: with no RAM free for its pages systemd cancels it and zram0 runs
  on as it was, a notice that it keeps its old settings until a reboot,
  when the generator reads the config. Then that unit on: it is the
  generator's, `generated`, so started, never enabled.
- `swappiness` set: `vm.swappiness` and `vm.page-cluster = 0` (one page
  per swap-in: read-ahead pays on a disk, not in RAM) through
  `ensure_sysctl`. `watermark_scale_factor` set: that sysctl too. 0
  writes neither.

`Zram.rules`: `priority` 0 to 32767, so above the swap file's (`swap`
sets none, and the kernel's is negative): zram fills first.
`swappiness` 0 to 200, `watermark_scale_factor` 0 to 3000, the kernel's
ranges.

## `system.oomd` — earlier OOM kills

```toml
[features.system.oomd]
enabled = true
```

Every systemd Linux (`platforms/linux/features/system/oomd.py`), off by default,
on in `profiles/laptop.toml`: on a server or a VM the kernel's OOM killer
decides. No settings: the limits
are in its templates. Part of systemd on Arch, no packages; Debian ships
it as `systemd-oomd`. `apply()`:

- Three drop-ins (`root:root` 644), each from its template:
  `/etc/systemd/oomd.conf.d/10-dotfiles.conf`, 60% pressure for 20 s
  instead of the stock 30 s; `/etc/systemd/system/-.slice.d/10-oomd.conf`,
  `ManagedOOMSwap=kill`: the largest swap user dies once swap is 90%
  full; `/etc/systemd/system/user@.service.d/10-oomd.conf`,
  `ManagedOOMMemoryPressure=kill` at 50%: pressure kills inside user
  sessions only, never a service.
- When one changed: `daemon-reload` and `try-restart` of
  `systemd-oomd.service`, which reads `oomd.conf.d` only when it starts.
  Then the service enabled and started.

## `system.dkms` — kernel modules built for every kernel

```toml
[features.system.dkms]
enabled = true
```

Arch only (`platforms/arch/features/system/dkms.py`), off by default; on
where a feature needs a module DKMS builds (`hardware.graphics` with
`nvidia`). No settings: its packages are `dkms` and the headers of every
installed kernel, `<pkgbase>-headers`, each kernel's `pkgbase` read from
`/usr/lib/modules/*/pkgbase` (`linux`, `linux-lts`, `linux-zen`, …), under
the sysroot. That is the one `packages()` reading the machine, and it
reads files only, no command: the kernels are the machine's, which no
host should have to repeat, and a kernel installed later gets its headers
on the next apply. It runs `before_packages`, since `hardware.graphics`,
which does too, requires it, and its headers are in the early
transaction, before the AUR builds a module. `apply()` only says, as a
notice, that no kernel was found when there is no `pkgbase`: DKMS then
builds nothing.

## `hardware.graphics` — the drivers of the GPUs

```toml
[features.hardware.graphics]
enabled = true
gpus    = ["intel", "nvidia"]  # amd, intel, nvidia, nouveau; several on a hybrid laptop
lib32   = true                 # their 32-bit drivers too, for steam and wine

[features.hardware.graphics.nvidia]
driver = "580xx"  # current, 580xx, 470xx or 390xx
```

Arch only (`platforms/arch/features/hardware/graphics.py`), off by
default; `gpus` is empty, `lib32` false and `driver` `current` by default.
Packages only; `apply()` only fails, before any change, while `gpus` is
empty (`features.hardware.graphics.gpus is empty`): `lib32` would then
meet steam's requirement with no driver, and `--noconfirm` would pick
`nvidia-utils`, which blacklists nouveau. It runs `before_packages`, so the provider of
`vulkan-driver` and `lib32-vulkan-driver` is installed, from the AUR too,
before a package depending on them (steam), which `--noconfirm` would
fill with the repositories' first provider, `nvidia-utils`. Per GPU, each
with its `lib32-` package when `lib32` is true:

| `gpus` | packages |
|---|---|
| `amd` | `mesa`, `vulkan-radeon` |
| `intel` | `mesa`, `vulkan-intel`, `intel-media-driver` (no `lib32-`) |
| `nouveau` | `mesa`, `vulkan-nouveau` |
| `nvidia`, `current` | `nvidia-open-dkms`, `nvidia-utils`, `libva-nvidia-driver` (no `lib32-`) |
| `nvidia`, `NNNxx` | `nvidia-NNNxx-dkms`, `nvidia-NNNxx-utils`, `libva-nvidia-driver` but for `390xx` |

- `current` is Turing and newer, from the repositories: `nvidia-open-dkms`
  is today's `nvidia-dkms`, which it provides and replaces; the name
  itself is no package, and `pacman -Si` does not find it, so the real
  name is the one written. `580xx` (Maxwell to Volta), `470xx` (Kepler)
  and `390xx` (Fermi) are the AUR's, built in the early phase.
- The module is always DKMS's, for whatever kernel is installed:
  `requires()` has `system.dkms` while `nvidia` is among `gpus`, and
  `Setting("packaging.pacman.multilib", True)` while `lib32` is true.
- `libva-nvidia-driver` (VA-API through NVDEC) needs the 470 series or
  newer, so `390xx` goes without it.
- `replaces()`, while `nvidia` is among `gpus`: the packages of the other
  branches, removed when installed so the chosen one installs without a
  conflict — for `current` every `nvidia-NNNxx-dkms`, `-utils` and
  `lib32-nvidia-NNNxx-utils`; for a legacy branch `nvidia-open-dkms`,
  `nvidia-open`, `nvidia-open-lts`, `nvidia-utils`, `lib32-nvidia-utils`
  and the other legacy branches'.
- `Graphics.rules`: `gpus` names from the four, none twice, not both
  `nvidia` and `nouveau` (the same card); `nvidia.driver` one of
  `current`, `580xx`, `470xx`, `390xx`.
- The kernel's side of NVIDIA (modeset, the suspend services, the
  initramfs) is not here: a `hardware.nvidia` of its own, later.

## `gaming.steam`, `gaming.gamemode`, `gaming.mangohud` — games

```toml
[features.gaming]
steam.enabled    = true
gamemode.enabled = true
mangohud.enabled = true
```

Arch only (`platforms/arch/features/gaming/`), each off by default and on
by itself; none requires another. No settings, packages from
the repositories, each 32-bit one from [multilib]:

- `steam`: `steam` and `ttf-liberation`, the font Arch's wiki names for
  it, so its `ttf-font` is not `--noconfirm`'s first provider.
  `requires()` `Setting("hardware.graphics.lib32", True)`: the 32-bit
  drivers of the host's GPUs, which `hardware.graphics` installs before
  the other packages, so steam's `vulkan-driver` and `lib32-vulkan-driver`
  are those, not the repositories' first; multilib comes with it,
  which `hardware.graphics` requires for `lib32`.
- `gamemode`: `gamemode` and `lib32-gamemode`. `requires()` multilib.
  `apply()`: `ensure_group_member("gamemode")`, the group the package
  makes (sysusers.d): its polkit rule lets only members switch the CPU
  governor, which gamemode does by default, and its limits.d lets them
  renice games; a notice to log in again when added.
- `mangohud`: `mangohud` and `lib32-mangohud`. `requires()` multilib.
  Its config, `~/.config/MangoHud/`, stays the user's; a game gets the
  overlay through `mangohud %command%` in its launch options.

## `desktop.fonts` — fonts and fontconfig

An example; by default `packages` and `nerd_fonts` are empty,
`nerd_version` is `v3.5.1`, `nerd_url` is the GitHub release's
`https://github.com/ryanoasis/nerd-fonts/releases/download/{version}/{name}.tar.xz`,
and `default` and `render` set nothing.

```toml
[features.desktop.fonts]
enabled      = true
packages     = ["noto-fonts-emoji"]
nerd_fonts   = ["JetBrainsMono"]        # on Arch, rather ttf-jetbrains-mono-nerd in packages
nerd_version = "v3.5.1"
nerd_url     = "https://mirror.example.org/nerd-fonts/{version}/{name}.tar.xz"

[features.desktop.fonts.default]
monospace = "JetBrainsMono Nerd Font"   # also sans_serif, serif, emoji
emoji     = "Noto Color Emoji"

[features.desktop.fonts.render]
antialias = true
hinting   = "slight"                    # none, slight, medium, full
subpixel  = "rgb"                       # rgb, bgr, vrgb, vbgr, none
```

Arch only (`platforms/arch/features/desktop/fonts.py`): `packages` are Arch's
names. Off by default. Its packages are `fontconfig`, `packages`, and
`curl` when there are Nerd Fonts; then `apply()`:

- Each of `nerd_fonts`: its URL is `nerd_url` with `{name}` the font and
  `{version}` `nerd_version`. Unless
  `~/.local/share/fonts/nerd-fonts/<name>/.source` holds that URL, the
  archive is downloaded with curl, retried, into that directory in place
  of what is there, unpacked by `tar -xf` (any compression tar knows),
  and the URL written to `.source`. Another version or URL downloads it
  again; a font taken out of the list stays. A dry run downloads nothing.
  On Arch the Nerd Fonts are packages too (`ttf-jetbrains-mono-nerd`), so
  pacman keeps them current; the download is for fonts or platforms
  without one.
- Any downloaded: `fc-cache` of `~/.local/share/fonts/nerd-fonts` as the
  user. The packages' fonts are cached by fontconfig's own pacman hook.
- `~/.config/fontconfig/conf.d/50-dotfiles.conf` from its template under
  `home/`: an `<alias>` preferring each family of `default` for its generic
  one (`sans_serif` is `sans-serif`), and one `<match target="font">`
  with `antialias`, `hinting` (`none` turns it off, the others are its
  `hintstyle`) and `subpixel` (`rgba`), each only when set. Fontconfig
  reads `~/.config/fontconfig/conf.d` at `50-user.conf`, before its
  `60-latin.conf` preferences, so ours come first.

`Fonts.rules`: `packages` and `nerd_fonts` names, `nerd_version` a
tag, `nerd_url` an `https://` URL with `{name}` and no placeholder but it
and `{version}`, the families without `<`, `>` or `&`, `hinting` and
`subpixel` from the names above; `Fonts.types` gives `default` and
`render` their keys, none with a default.

## `shell.zsh` — zsh and oh-my-zsh

An example; by default `shell` is `/usr/bin/zsh`, `plugins` and `extras`
are empty, `theme.name` is `robbyrussell`, `theme.repo` and `theme.branch`
are empty.

```toml
[features.shell.zsh]
enabled = true
shell   = "/usr/bin/zsh"
plugins = ["git"]
extras  = ["zsh-autosuggestions", "zsh-syntax-highlighting", "zsh-completions"]

[features.shell.zsh.theme]
name   = "mytheme/mytheme"                       # <dir>/<name>: a theme of the repo
repo   = "https://example.org/someone/mytheme.git"
branch = ""                                      # the repo's default
```

Every Linux (`platforms/linux/features/shell/zsh.py`): the extras' scripts are
`<extras_dir>/<extra>/<extra>.zsh`, `extras_dir` being
`/usr/share/zsh/plugins` (Arch, Void) or `/usr/share` on Debian
(`platforms/debian/features/shell/zsh.py`, a subclass); Debian has no
zsh-completions, so asking for it there fails at the install. Off by
default, on in `profiles/base.toml`. Of the user's files it writes two
only: `~/.config/zsh/dotfiles.zsh`, and one line of `~/.zshrc`. Whatever
a theme or a plugin needs besides, its own settings files included, the
user sets up in `~/.zshrc`. Its packages are `zsh`, `git` and the
extras; then `apply()`:

- `~/.oh-my-zsh/oh-my-zsh.sh` missing: `git clone --depth 1` of oh-my-zsh
  there as the user, retried, a directory cut off halfway removed first.
  It is never pulled: `omz update` is the user's, and never cloned again
  once there: it may be the user's own, with their `custom/`. A dry run
  clones nothing.
- The theme: without `repo`, one of oh-my-zsh's own, nothing cloned. With
  `repo`, `name` is `<dir>/<name>` (else apply fails): the theme `<name>`
  of `repo` cloned the same way into `~/.oh-my-zsh/custom/themes/<dir>`
  (oh-my-zsh loads `custom/themes/<dir>/<name>.zsh-theme` for
  `ZSH_THEME=<dir>/<name>`), `--branch` when `branch` is set; cloned again in place
  of what is there whenever `git remote get-url origin` is not `repo`, or
  the branch checked out is not `branch`. Never pulled.
- `~/.config/zsh/dotfiles.zsh` from `home/.config/zsh/dotfiles.zsh.j2`:
  `ZSH`, `ZSH_THEME`, `plugins`, `source $ZSH/oh-my-zsh.sh`, then the
  extras' scripts, every `~/.config/zsh/dotfiles.d/*.zsh` (other
  features' hooks), syntax highlighting last. zsh-completions is only its
  package: its functions are in zsh's `fpath` already.
- `source ~/.config/zsh/dotfiles.zsh` in `~/.zshrc`, at the top, so the
  rest of the file stays the user's and overrides ours; a missing
  `~/.zshrc` is created with that line alone.
- `shell` not an executable file: apply fails before `chsh`, in a dry run
  too; zsh's package is installed by then, so it is a typo. A login shell
  other than `shell`: `chsh -s <shell>` as root, and a notice to log out
  and back in. Both paths are compared resolved, so
  `/bin/zsh` is `/usr/bin/zsh` where `/bin` links to `/usr/bin`.

`Zsh.rules`: `shell` an absolute path; `theme.name` one such name or two joined by `/`, each of
`plugins` letters, digits, `.`, `_` and `-`; `theme.repo` empty or an
`https://` URL; `theme.branch` empty or a branch name; `extras` names
from the three above.

## `shell.command_not_found` — the package of a missing command

```toml
[features.shell.command_not_found]
enabled = true
shells  = ["zsh", "bash"]
```

Arch only (`platforms/arch/features/shell/command_not_found.py`), off by
default, on in `profiles/arch.toml`; `shells` is `["zsh"]` by default. No
packages. It requires `package_tools.pkgfile`, whose database and handlers it
uses, and `shell.zsh` only while `zsh` is one of `shells`: `requires()` reads its settings.
`apply()` writes the hook of each shell:

- zsh: `~/.config/zsh/dotfiles.d/command-not-found.zsh`, which zsh's
  snippet sources, sourcing `/usr/share/doc/pkgfile/command-not-found.zsh`.
- bash: `source /usr/share/doc/pkgfile/command-not-found.bash` at the end
  of `~/.bashrc` (`files.line`; a missing one is created with it alone).
  bash has no feature, and no snippet of ours: it is on every system, and
  what `~/.bashrc` reads before the line stays the user's.

A command the shell does not find then prints the packages that have it.
A shell taken out of `shells` keeps its hook: off never undoes.

`CommandNotFound.rules`: `shells` not empty, only `zsh` and `bash`, each
once.

## Project Structure

```
dotfiles/platforms/<p>/features/<group>/__init__.py           empty: a group
dotfiles/platforms/arch/features/packaging.py                 Packaging: rules, types, drop-ins, multilib; before_packages
system/etc/pacman.conf.d/options.conf.j2                      its templates
system/etc/pacman.conf.d/multilib.conf.j2
system/etc/makepkg.conf.d/dotfiles.conf.j2
dotfiles/platforms/arch/features/package_tools/reflector.py   Reflector: rules, config, timer, refresh
system/etc/xdg/reflector/reflector.conf.j2                    its templates
system/etc/systemd/system/reflector.timer.d/override.conf.j2
dotfiles/platforms/linux/features/development/rustup.py       Rustup: rustup, its default toolchain
dotfiles/platforms/arch/features/development/rustup.py        Rustup: Linux's, in place of rust
dotfiles/platforms/void/features/development/rustup.py        Rustup: rustup-init first, then Linux's
dotfiles/platforms/arch/features/package_tools/paru.py        Paru: built from the AUR while it does not run
dotfiles/platforms/linux/features/system/no_beep.py           NoBeep: blacklist, unload
system/etc/modprobe.d/nobeep.conf.j2                          its template
dotfiles/platforms/arch/features/package_tools/pkgfile.py     Pkgfile: timer, first download
dotfiles/platforms/linux/features/development/git.py          Git: our gitconfig, its include
home/.config/git/dotfiles.gitconfig.j2                        its template
dotfiles/platforms/linux/features/system/locale.py            Locale: rules, locale-gen, LANG, console, timezone
dotfiles/platforms/debian/features/system/locale.py           Locale: Linux's, LANG in /etc/default/locale, no console
system/etc/locale.conf.j2                                     its templates
system/etc/default/locale.j2
system/etc/vconsole.conf.j2
dotfiles/platforms/linux/features/system/timesyncd.py         Timesyncd: the service
dotfiles/platforms/debian/features/system/timesyncd.py        Timesyncd: Linux's, with its package
dotfiles/platforms/linux/features/system/swap.py              Swap: rules, subvolume, units, the file
system/etc/systemd/system/swap.mount.j2                       its templates
system/etc/systemd/system/swap-swapfile.swap.j2
dotfiles/platforms/linux/features/system/zram.py              Zram: rules, config, the unit, sysctls
dotfiles/platforms/debian/features/system/zram.py             Zram: Linux's, with Debian's package
system/etc/systemd/zram-generator.conf.j2                     its template
dotfiles/platforms/linux/features/system/oomd.py              Oomd: drop-ins, restart, the service
dotfiles/platforms/debian/features/system/oomd.py             Oomd: Linux's, with its package
system/etc/systemd/oomd.conf.d/10-dotfiles.conf.j2            its templates
system/etc/systemd/system/-.slice.d/10-oomd.conf.j2
system/etc/systemd/system/user@.service.d/10-oomd.conf.j2
dotfiles/platforms/arch/features/desktop/fonts.py             Fonts: Nerd Fonts, fc-cache, fontconfig
home/.config/fontconfig/conf.d/50-dotfiles.conf.j2            its template
dotfiles/platforms/linux/features/shell/zsh.py                Zsh: oh-my-zsh, our part of ~/.zshrc, chsh
dotfiles/platforms/debian/features/shell/zsh.py               Zsh: Linux's, with Debian's extras_dir
home/.config/zsh/dotfiles.zsh.j2                              its template
dotfiles/platforms/arch/features/shell/command_not_found.py   CommandNotFound: rules, pkgfile's hooks for zsh and bash
home/.config/zsh/dotfiles.d/command-not-found.zsh.j2          its template
dotfiles/defaults.toml                                        every feature and its settings
dotfiles/platforms/arch/features/system/dkms.py               Dkms: dkms, each kernel's headers from its pkgbase
dotfiles/platforms/arch/features/hardware/graphics.py         Graphics: rules, the drivers per GPU and branch
dotfiles/platforms/arch/features/gaming/steam.py              Steam: steam, its font
dotfiles/platforms/arch/features/gaming/gamemode.py           Gamemode: gamemode, the group
dotfiles/platforms/arch/features/gaming/mangohud.py           Mangohud: mangohud
tests/test_features.py                                        each feature against a fake machine
tests/test_apply.py                                           test_real_features_are_consistent
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
- rustup on Void: `rustup-init` once, then `~/.cargo/bin/rustup` checked
  by its path, nothing the second time.
- rustup: `default stable` once, nothing while it is the default; another
  toolchain switched to, a dated nightly not taken for `nightly`.
- paru: built from the AUR while `paru --version` fails, not once it runs;
  a dry run only checks.
- no_beep: the blacklist, a loaded driver unloaded once, nothing the
  second time; a driver in use is a notice.
- pkgfile: the timer enabled and one download on the first apply,
  nothing once a database is there; a failed download is a notice.
- git: `[user]` with both set, the include on top of an existing config,
  nothing the second time; nothing set: no `[user]`, the config created
  with the include alone.
- locale: the line uncommented, `locale-gen`, LANG, KEYMAP, the console
  set up and the zone linked, nothing the second time; a locale missing
  from `locale.gen` added at its end; another `lang` rewrites
  `locale.conf` alone, no `locale-gen`; `FONT=` with a
  font, a missing one a notice; a failed console setup is no error; an
  unknown zone fails before any change; the packages are the console's on
  Arch and `locales` on Debian; on Debian LANG in `/etc/default/locale`, no
  `vconsole.conf`, a console asked for a notice. `test_config`: a
  `timezone` with `..`, a leading `/` or an empty part is refused.
- timesyncd: the service enabled once, nothing while it runs; no package
  on Arch, `systemd-timesyncd` on Debian.
- swap: the subvolume created, both units, `daemon-reload`, the file and
  both units enabled, the `.swap` with no `Priority=`; nothing changed and
  no command but checks the second time; a file of the size set left
  alone, one of another size stopped, removed and made again, kept with a
  notice while swapoff fails, only reported in a dry run, its unit
  started again; within a page of the size left alone (no recreating on
  every apply); `mkswapfile` failing after `rm` fails the feature, swap
  off, the next apply creating the file anew; `size` in bytes and the
  shown size for each suffix; an existing
  `@swap` kept; an
  empty `size` or a root that is not btrfs fails before any change; a
  line in fstab a notice; a dry run lists no subvolume. `test_config`: a
  `size` mkswapfile would not take is refused.
- zram: the config, `daemon-reload` and a restart of the unit, no
  sysctl by default; nothing but checks the second time, the unit
  `generated`; the sysctls of `swappiness` and `watermark_scale_factor`
  when set; a failed restart a notice, the sysctls still set;
  `zram-generator` on Arch, `systemd-zram-generator` on Debian.
  `test_config`: a negative `priority`, and `swappiness` or
  `watermark_scale_factor` past the kernel's range, are refused.
- oomd: the three drop-ins, `daemon-reload`, `try-restart` and the
  service enabled, nothing the second time; no package on Arch,
  `systemd-oomd` on Debian.
- fonts: a Nerd Font downloaded, unpacked and cached once, again for
  another version or URL, not in a dry run; `curl` among the packages only with
  Nerd Fonts; the fontconfig file with only what is set, `hinting = none`
  without a `hintstyle`.
- zsh: one clone, the snippet with the plugins chosen, the source line on
  top of an existing `~/.zshrc` or alone in a new one, `chsh` and its
  notice; nothing the second time; a dry run clones nothing and leaves a
  half clone alone. A theme's repo cloned into `custom/themes/<dir>`, and
  nothing written but the snippet and `~/.zshrc`'s line. Another branch or
  origin cloned again, `--branch` passed; a built-in theme clones nothing;
  a repo's theme without `<dir>/` fails. Another `shell` set: `chsh -s`
  with it; one that is not there fails before `chsh`, in a dry run too.
  On Debian the extras are sourced from `/usr/share/<extra>/`.
- command_not_found: the hook sourcing pkgfile's handler, nothing the
  second time; for bash its line at the end of an existing `~/.bashrc`,
  once, and no zsh hook; both shells, both hooks; `shell.zsh` required
  only with `zsh` among `shells`. `test_config`: an empty `shells`, another
  shell or one twice refused.
- dkms: `dkms` and `linux-headers` for a `linux` pkgbase, both kernels'
  headers with `linux-lts` too; no pkgbase, `dkms` alone and a notice;
  `before_packages`.
- graphics: the packages of each GPU, with and without `lib32`; `current`
  and `580xx` with their `replaces()`; `390xx` without
  `libva-nvidia-driver`; `system.dkms` required only with `nvidia`,
  multilib only with `lib32`; nothing for an empty `gpus`;
  `before_packages`. `test_config`: an unknown GPU, one twice, `nvidia`
  with `nouveau` and an unknown `driver` refused.
- graphics: an empty `gpus` fails before any change.
- gaming: each feature's packages and its requirement; gamemode adds the
  user to `gamemode`. `test_apply`: steam on without
  `hardware.graphics.lib32` refused by `check`.
- `test_real_features_are_consistent`: every schema feature has a module
  and every module a schema table with `enabled`, but `packaging`; every
  override subclasses its base's class; only `package_tools.paru`
  (`packaging`, `development.rustup`), `shell.command_not_found`
  (`package_tools.pkgfile`, and `shell.zsh` by default), `gaming.steam`
  (`hardware.graphics`, through its setting), `gaming.gamemode` and
  `gaming.mangohud` (`packaging`, through multilib) and
  `hardware.graphics` (`packaging`, through multilib, with `lib32`)
  require others.
- Discovery (`test_apply`): a feature in a group named by its path, a
  group in a group, `_` modules and groups skipped at any depth, an
  override that does not subclass its base's refused; a group's table
  holds only its features'.
- `Setting` (`test_apply`): met, unmet with `true` and with `false`, a key
  no file sets unmet, a key that is not a boolean and an unknown `op`
  refused, a disabled owner reported, the requiring feature run after
  its owner and failed with it, a cycle through an owner found.
- `before_packages` (`test_apply`): run before the install, its
  packages in their own transaction before the others' (`installs ==
  [["tool"], ["app"]]`), its AUR packages built before the others'
  transaction, `depends()` asked only after both; requiring a feature
  without the flag refused; its failure, or its transaction's, blocks
  what runs after it, not the other install; a dry run prints both
  `packages:` lines.

## Boundaries

- **Always:** templates for every file written; check before mutating;
  root only through `shell.as_root`.
- **Ask first:** editing `pacman.conf` or `makepkg.conf` beyond the
  `Include` lines; an automatic `-Syu` outside enabling multilib.
- **Never:** `pacman -Sy` without `-u`.

## Decisions

1. **`packaging` is an ordinary feature**, not the platform's setup. A
   feature that needs it says so in `requires()`, as `package_tools.paru`
   does for its `MAKEFLAGS` and `OPTIONS`, or requires one of its settings
   (`Setting("packaging.pacman.multilib", True)` for what is in
   [multilib]). It runs `before_packages`, so its multilib is there for the
   install of the same apply.
6. **Groups are directories, no features.** A feature's name is its path,
   so nothing declares it; a group has no switch, so a feature has one.
   Leaves keep their names (`development.rustup`, not `.rust`), so
   classes, templates and their tests stay as they are. The group of
   reflector, paru and pkgfile is `package_tools`: `pacman` would read
   like `packaging.pacman`'s table, `packages` like `packages()`.
7. **No migration code.** The resolved `~/.config/dotfiles/config.toml`
   keeps the old flat keys and fails with `unknown key` after the move;
   `dotfiles init <host>` writes it again.
2. **What is not set writes nothing**: a key no host or profile sets
   leaves the main file's value, so a host sets only what it wants to
   change. multilib is the exception: `false` empties its drop-in, since
   the repository there is ours.
3. **Valueless options are a list** (`flags`), since TOML has no key
   without a value and `false` could not turn one off anyway.
4. **`jobs` has no shell expressions** (`"$(nproc)"`): a number or a
   percent, resolved at the apply.
5. **Another feature's zsh hook is a file of `~/.config/zsh/dotfiles.d`**,
   which zsh's snippet sources: a feature gets only its own settings, so
   it cannot add to zsh's template, and zsh need not know who adds what.
