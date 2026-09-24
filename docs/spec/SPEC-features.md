# Spec: `features` — every feature of the schema

Status: draft 2026-09-24. Module of the [capability map](CAPABILITY-MAP.md);
depends on `packages` and `render`.

## Objective

Every `features.<name>` in `dotfiles/defaults.toml` does what its line in
the schema says, on Arch, through the engine: a check first, a change only
when the check fails, root only through `as_root`. After this module
`dotfiles apply` on hyper-lin brings a fresh Arch install to the machine
the host file describes, and a second apply prints nothing.

User stories:

- A new CLI tool on a host is one line in its host file; a new tool for
  every host is one file of four lines in `dotfiles/features/`.
- A failed network step in one feature (a clone, a toolchain download)
  leaves a notice and the rest of the apply goes on.
- `dotfiles apply --dry-run` on hyper-lin lists every change the real run
  would make and runs no sudo.

## Tech Stack

As `engine` and `packages`: stdlib only (`json` for the Firefox policy and
VS Code's storage, `re`, `shutil`, `pathlib`). No new dependency.

## Structure

One module per feature, `dotfiles/features/<name>.py`, one `Feature`
subclass, its name the feature's: the runner gates it by the file name, as
today. A feature that only installs packages is four lines:

```python
class Htop(Feature):
    class Arch:
        def packages(self):
            return ["htop"]
```

Three modules are not in the schema's `features` table and always run,
reading their own switch (the runner already allows this):

| Module | Switch | |
|---|---|---|
| `ssh_key.py` | `ssh.generate_key` | an ed25519 key when `~/.ssh` has none |
| `rbw.py` | `secrets.backend == "rbw"` | `rbw`, `pinentry` |
| — | `features.pacman`, `makepkg`, `reflector` | done by `Arch.setup()` (`packages`), no module |

A setting that makes a feature impossible (`gaming` without
`pacman.multilib`) returns no packages and fails in `apply` with a message
naming the setting, so nothing half-installs.

Features read their settings from `self.cfg["features"][name]`; the
strategy gets the same config, so `packages()` may depend on it
(`fcitx5` adds `fcitx5-chinese-addons` when `locale.languages` has
`chinese`).

## Features

Packages are Arch names. "Service" is `strategy.ensure_service(unit)`;
"group" is `strategy.ensure_group_member(group)`. Every file written is
`root:root` 644 unless it is in `$HOME`.

### Packages only (batch 1)

| Feature | Packages | Also |
|---|---|---|
| `cli_tools` | jq yq tmux direnv zoxide eza fzf bat tealdeer ripgrep fd unzip zip 7zip rsync wget curl ncdu duf just git-delta lazygit git-lfs shellcheck luacheck lychee ffmpeg pipewire-jack cmatrix sbctl nano vim less tree clock-rs-git | replaces jack2 |
| `neovim` | neovim git tree-sitter-cli | |
| `go` | go delve | |
| `android` | android-tools android-udev | group adbusers |
| `gh` | github-cli | |
| `cpp_gcc` | gcc gdb make cmake meson ninja cppcheck | |
| `cpp_clang` | clang lldb lld llvm make cmake meson ninja cppcheck | |
| `jdk` | jdk-openjdk | |
| `dotnet` | dotnet-sdk | |
| `kotlin` | kotlin gradle | |
| `sqlite` | sqlite | |
| `tracing` | valgrind strace ltrace perf | |
| `nmap`, `mtr`, `tcpdump`, `htop`, `btop`, `iotop`, `veracrypt`, `sccache` | the same name | |
| `dig` | bind | |
| `claude_code` | claude-code | |
| `noctalia` | noctalia | |
| `fcitx5` | fcitx5 fcitx5-gtk fcitx5-qt fcitx5-configtool, + fcitx5-chinese-addons with `chinese` | |
| `fonts` | noto-fonts-emoji noto-fonts-cjk | |
| `nerd_font` | ttf-firacode-nerd ttf-nerd-fonts-symbols-mono | |
| `audio` | pipewire-pulse pipewire-alsa pipewire-jack wireplumber playerctl brightnessctl | replaces jack2 |
| `kitty`, `evince`, `vlc`, `termusic`, `loupe`, `feh`, `discord`, `qbittorrent`, `yazi` | the same name | |
| `onlyoffice` | onlyoffice-bin | |
| `wireshark` | wireshark-qt qt6-multimedia-ffmpeg | group wireshark |
| `claude_desktop` | claude-desktop | |
| `sqlitebrowser` | sqlitebrowser | |
| `telegram` | telegram-desktop | |
| `doublecmd` | doublecmd-qt6 | |
| `mission_center` | mission-center | |
| `obs_studio` | obs-studio pipewire-jack | replaces jack2 |
| `gaming` | steam gamemode mangohud lib32-mangohud ttf-liberation | none, and `die`, without `pacman.multilib` |
| `rbw` (module) | rbw pinentry, with `secrets.backend = "rbw"` | |

AUR packages (`clock-rs-git`, `claude-code`, `onlyoffice-bin`,
`claude-desktop`) are listed like any other; `install` takes them from the
AUR, or fails naming them and `features.aur`.

### Packages and a unit (batch 2)

| Feature | Packages | Unit |
|---|---|---|
| `bluetooth` | bluez bluez-utils | bluetooth.service |
| `fwupd` | fwupd | fwupd-refresh.timer |
| `timesyncd` | — | systemd-timesyncd.service |
| `btrfs_scrub` | btrfs-progs | btrfs-scrub@-.timer |
| `paccache` | pacman-contrib | paccache.timer |
| `pkgfile` | pkgfile | pkgfile-update.timer; `pkgfile -u` as root while `/var/cache/pkgfile` is empty (the timer only refreshes) |
| `yubikey` | yubikey-manager pcsclite ccid | pcscd.socket |
| `docker` | docker docker-buildx docker-compose | docker.service; group docker |
| `tailscale` | tailscale | tailscaled.service; `tailscale set --operator=<user>` as root unless `tailscale debug prefs` already names the user |

### System configuration (batch 3)

- **`locale`**
  - `ensure_line` on `/etc/locale.gen` for each of `locales`, matching
    the commented-out line too; `locale-gen` as root when any changed.
  - `/etc/locale.conf`: `LANG=`.
  - `console.packages` installed.
  - `/etc/vconsole.conf`: `KEYMAP=`, plus `FONT=` when `console.font` is
    set. When it changed:
    - `systemctl restart systemd-vconsole-setup.service` (a failure is
      ignored: no console to set up in a graphical session);
    - a font missing from `/usr/share/kbd/consolefonts` is a notice;
    - with an `sd-vconsole` or `consolefont` hook in
      `/etc/mkinitcpio.conf`, a notice to run `mkinitcpio -P`.
  - `/etc/localtime` → `/usr/share/zoneinfo/<timezone>`; `hwclock
    --systohc` when it changed.
- **`oomd`**
  - `/etc/systemd/oomd.conf.d/10-pressure.conf`:
    `DefaultMemoryPressureLimit=60%`, `DefaultMemoryPressureDurationSec=20s`.
  - `/etc/systemd/system/-.slice.d/10-oomd.conf`: `ManagedOOMSwap=kill`.
  - `/etc/systemd/system/user@.service.d/10-oomd.conf`:
    `ManagedOOMMemoryPressure=kill`, `ManagedOOMMemoryPressureLimit=50%`.
  - When any changed: `daemon-reload`, `try-restart systemd-oomd.service`
    (oomd reads its drop-ins only at start).
  - Service systemd-oomd.service.
- **`sshd`**
  - openssh.
  - `/etc/ssh/sshd_config.d/dotfiles.conf`: `PasswordAuthentication
    yes|no`, `PermitRootLogin <permit_root_login>`. Turning password
    login off adds a notice to check a key login first.
  - `reload sshd.service` when the file changed and sshd is active.
  - Service sshd.service.
- **`resolved`**
  - Service systemd-resolved.service.
  - `/etc/resolv.conf` → `/run/systemd/resolve/stub-resolv.conf`.
  - `/etc/NetworkManager/conf.d/dns.conf`: `[main]` `dns=systemd-resolved`.
    When it changed and NetworkManager is active: restart it, then
    `nm-online -s -q -t 30`; still offline is a notice.
- **`zram`**
  - zram-generator.
  - `/etc/systemd/zram-generator.conf`, `[zram0]` with `zram-size`,
    `compression-algorithm`, `swap-priority`. When it changed:
    `daemon-reload`, restart `systemd-zram-setup@zram0.service`.
  - Service `systemd-zram-setup@zram0.service`.
  - `swappiness > 0`: `vm.swappiness` and `vm.page-cluster = 0`.
  - `watermark_scale_factor > 0`: `vm.watermark_scale_factor`.
- **`thp`**
  - `/etc/tmpfiles.d/thp.conf`:
    `w /sys/kernel/mm/transparent_hugepage/enabled - - - - <mode>`.
  - When `[<mode>]` is not the one selected in that sysfs file:
    `systemd-tmpfiles --create` on the file.
  - `reserve > 0`: `vm.nr_hugepages`.

### Boot, disks and drivers (batch 4)

- **`luks_discard`** — `/etc/kernel/cmdline` gets `:discard` on every
  `rd.luks.options=<uuid>:…` of each `rd.luks.name=<uuid>`, or a new
  `rd.luks.options=<uuid>:discard` at the end of its one line. The file
  keeps its mode and owner. A notice to rebuild the initramfs when
  something changed. There are three cases where nothing changes and a
  notice says what to do by hand:
  - no `sd-encrypt` hook in mkinitcpio.conf;
  - no `/etc/kernel/cmdline`;
  - no `rd.luks.name=` in it.
- **`swap`**
  - The swap file lives on its own `@swap` subvolume, so it does not block
    snapshots of `/`.
  - `size` empty, or `/` not btrfs → `die` naming the setting.
  - While `swap.mount` is not active: create `@swap` when `btrfs
    subvolume list /` lacks it, through a temporary mount of subvolid 5.
  - Units `/etc/systemd/system/swap.mount` (`UUID=` of `/`,
    `subvol=/@swap`, `noatime`) and `swap-swapfile.swap`;
    `daemon-reload` when they changed.
  - `/swap` exists; service `swap.mount`.
  - `btrfs filesystem mkswapfile --size <size>` when the file does not
    exist; service `swap-swapfile.swap`.
  - Notices: an `/etc/fstab` line for `/swap`, and any other active swap
    file on the root subvolume.
- **`plymouth`**
  - plymouth.
  - `plymouth` goes into mkinitcpio.conf's `HOOKS=` after `systemd`, else
    after `udev`, else after `base`. The line is edited in place with
    `ensure_line`.
  - `plymouth-set-default-theme -R bgrt` when the theme is not bgrt or
    the hook was just added; that rebuilds the initramfs. A notice about
    `quiet splash`.
- **`nvidia`**
  - The GPU is read without any package:
    - `/sys/bus/pci/devices/*`: vendor `0x10de`, class `0x03…`;
    - the name from `/usr/share/hwdata/pci.ids` (hwdata ships with
      systemd).
  - No NVIDIA GPU → no packages, nothing to do.
  - Generation → driver:

    | GPU | Driver | 32-bit |
    |---|---|---|
    | RTX 20+, GTX 16, MX300+ | nvidia-dkms | lib32-nvidia-utils |
    | GTX 9/10, MX100–200 | nvidia-580xx-dkms | lib32-nvidia-580xx-utils |
    | GTX 6/7 | nvidia-470xx-dkms | lib32-nvidia-470xx-utils |
    | GTX 4/5 | nvidia-390xx-dkms | lib32-nvidia-390xx-utils |
    | GeForce 8/9/100–300 | nvidia-340xx-dkms | — |
    | unknown | nvidia-dkms, with a notice | lib32-nvidia-utils |

  - Headers for the running kernel (`os.uname().release`: `-zen`, `-lts`,
    `-hardened` or plain), plus nvtop.
  - The 32-bit package only with `pacman.multilib`, otherwise a notice.
  - A driver that was missing before the apply → a notice to reboot.
- **`snapper`** (with the snapshot pair below)
  - `/` not btrfs → `die`. An active swap file on the root subvolume → a
    notice.
  - snapper, snap-pac.
  - `/etc/snapper/configs/root` missing → `snapper -c root create-config
    /`. An existing `/.snapshots` mount is unmounted around it and put
    back, and the directory is set to 750.
  - `get-config` (as the user; as root until `ALLOW_USERS` is set), then
    `set-config` for each key that differs:
    - `TIMELINE_CREATE`, `NUMBER_LIMIT`, `NUMBER_LIMIT_IMPORTANT`;
    - `ALLOW_USERS=<user>`;
    - `SYNC_ACL=yes`.
  - `/etc/snap-pac.ini`: `[root]` with `important_packages` and
    `important_commands` as JSON lists.
  - `/usr/local/lib/dotfiles/snapper-pre` (755) and
    `/etc/pacman.d/hooks/00-dotfiles-snapper-pre.hook`.
  - Services snapper-cleanup.timer, and snapper-timeline.timer with
    `timeline`.

### The snapshot pair around an apply (batch 4)

With `features.snapper`, `apply` runs its phases inside
`snapshot.pair(cfg)`, a context manager in `dotfiles/snapshot.py`; the
environment variables `apply` sets for snapper today move there.

- **Enter.** Only when snapper works (`snapper -c root list` as the user)
  and the runtime dir exists:
  - a state file left by a dead apply: its pre snapshot is deleted and
    the file removed;
  - the state file is written: `pid=`, and `log=` (the size of
    `/var/log/pacman.log`).
- **The pacman hook** runs as root before every transaction. It takes one
  pre snapshot per apply, `pre=` in the state file, and only when a
  package changes. So an apply that installs nothing takes no snapshots.
- **Exit** (also after a failure):
  - no `pre=`, or another apply's state file → nothing;
  - otherwise a post snapshot for it. When pacman.log since `log=` shows
    a package of `important_packages` installed, upgraded or removed,
    the pair is marked important.

The hook is a seven-line POSIX `sh` script written into the system by the
feature, like the niri scripts in `home/`. pacman executes it; the tool
itself runs no shell.

### The user's environment (batch 5)

- **`zsh`**
  - zsh and git.
  - `chsh -s <zsh>` as root when the passwd entry differs; a notice about
    the next login.
  - Shallow clones, never updated here (`omz update` does that):
    - oh-my-zsh into `~/.oh-my-zsh`;
    - powerlevel10k, zsh-autosuggestions and zsh-syntax-highlighting into
      its `custom/`.
  - Each clone goes into a temp dir first and is moved into place, so a
    clone cut off halfway is never taken for a finished one. It is
    retried, then `defer`red.
- **`uv`** — uv; `uv python install` when `uv python list --only-installed
  --managed-python` is empty (retried, then deferred).
- **`fnm`**
  - fnm.
  - LTS node installed and made the default.
  - pnpm through `npm install -g` on it.
  - The network steps are retried, then deferred.
- **`rustup`**
  - rustup, replacing rust.
  - `rustup default stable` when there is no default toolchain.
  - `rustup toolchain install stable` again when `rustc -V` or `cargo -V`
    does not run under it.
- **`libvirt`**
  - libvirt qemu-desktop pipewire-jack virt-manager dnsmasq edk2-ovmf
    swtpm, replacing jack2.
  - Services libvirtd.service and virtlogd.socket; group libvirt.
  - The `default` network autostarts and is active. `virsh -c
    qemu:///system` runs as the user, or as root until the group
    membership is live.
  - No `vmx`/`svm` in `/proc/cpuinfo` → a notice.
- **`ssh_key`** (module) — with `ssh.generate_key` and no
  `~/.ssh/id_ed25519`, `ssh-keygen -t ed25519`:
  - with `ssh.passphrase`: ssh-keygen asks for the passphrase itself, and
    only with a terminal (otherwise a notice with the command);
  - without it: `-N ""`.

  Then a notice with the public key for `data/ssh-keys.toml`.
- **`ssh_agent`**
  - `ssh-agent.socket` as a user service.
  - Without a systemd user session: a notice with the command.
  - Enabled now: a notice to log in again for `SSH_AUTH_SOCK`.

### Desktop (batch 6)

- **`niri`**
  - niri xwayland-satellite xdg-desktop-portal-gtk xdg-utils wl-clipboard
    gnome-themes-extra.
  - gsettings `color-scheme 'prefer-dark'` and `gtk-theme
    'Adwaita-dark'`.
- **`greetd`**
  - The greeter's packages:
    - `tuigreet` → greetd-tuigreet, command `tuigreet --remember
      --remember-session --sessions
      /usr/share/xsessions:/usr/share/wayland-sessions`;
    - `noctalia-greeter` → noctalia-greeter, command
      `noctalia-greeter-session`, with `-- --session S --user U` when
      those are set;
    - any other greeter → `die`.
  - `/etc/greetd/config.toml`: `[terminal] vt = 1`, `[default_session]`
    with the command and `user = "greeter"`.
  - `systemctl enable greetd.service` when it is not enabled: enabled,
    not started, since this apply may run on that VT. A notice to reboot.
- **`firefox`**
  - firefox.
  - `/usr/lib/firefox/distribution/policies.json`: every pref of
    `data/firefox.toml` as `{"Value": v, "Status": "default"}` under
    `policies.Preferences`, written with `json.dumps(indent=2)`. A new
    default, nothing locked.

### VS Code (batch 7)

`vscode`: visual-studio-code-bin (AUR); profiles and extensions from
`data/vscode.toml` (`extensions`, `excluded`, `profiles.<name>.extensions`
/ `.settings`).

- **Profiles.** Each profile is registered in
  `~/.config/Code/User/globalStorage/storage.json`
  (`userDataProfiles`: name, a slug of it as location, `useDefaultFlags`
  for keybindings, snippets and tasks, and for settings when the profile
  has none of its own).
  - A profile already registered keeps its location.
  - Unlisted profiles are kept.
  - While VS Code runs (its `SingletonLock` points at a live pid), a
    missing profile is a `die`, because VS Code would overwrite the file.
- **Settings.** A profile with settings gets `settings.json` = the
  Default profile's `home/.config/Code/User/settings.json` merged with
  its own.
- **Extensions.**
  - `code [--profile P] --install-extension …` for what `--list-extensions`
    lacks: 5 attempts, 30 s apart and growing.
  - A failure is collected and becomes one `defer` at the end.
  - `excluded` ids are uninstalled from the Default profile.
- **Shared extensions.** They are flagged `isApplicationScoped` in
  `~/.vscode/extensions.json`, together with the members of the extension
  packs among them, found through each `package.json`'s `extensionPack`.
  Per-profile entries for them are dropped from each profile's
  `extensions.json`.

## Delivery

A branch and a PR per batch, in the order above, each stacked on the
previous one until it merges. A batch is one or a few commits; each
feature has its test. `data/firefox.toml` and `data/vscode.toml` come with
their batches (the second as TOML, like every other registry).

## Testing Strategy

- **Every module** (`test_real_features_are_consistent`):
  - the class name is the module's name in CamelCase;
  - the feature is in the schema, or is one of the three modules above;
  - every schema feature has a module, except the three that `Arch.setup`
    handles.
- **Packages-only features:** one parametrized test over all of them
  checks `packages()` against the table above, and `replaces()` where the
  table says so.
- **Each feature with an `apply`:**
  - a fake `_run` and a temp `SYSROOT`;
  - the first run makes the changes, a second run prints nothing;
  - the notices and the `die`/`defer` paths named in this spec.
- **Pure functions that decide something** have table tests: the nvidia
  generation from a GPU name, the snapper important-package check, the
  luks cmdline edit, the plymouth HOOKS edit.
- **`snapshot.pair`:** a fake snapper and a temp runtime dir cover
  - nothing without a pre;
  - a post for a pre;
  - important from the pacman.log;
  - a stale state file from a dead pid.
- **By hand, at the end of each batch:** `apply --dry-run` with the
  hyper-lin config on a real Arch (read-only); no sudo.

## Boundaries

- **Always:**
  - check before changing;
  - root through `as_root` only;
  - network steps retried, then deferred when nothing later needs them;
  - a notice for anything the user must do by hand (reboot, relogin,
    `mkinitcpio -P`).
- **Ask first:**
  - removing anything but a replaced package or an excluded extension;
  - rebuilding the initramfs outside plymouth's own command;
  - a feature not in the schema.
- **Never:**
  - start greetd from an apply;
  - lock a Firefox pref;
  - update a clone that exists;
  - write a secret or a private key anywhere but `~/.ssh`.

## Success Criteria

1. Every feature in `dotfiles/defaults.toml` has its module, and the
   consistency test proves it.
2. The dry run with the hyper-lin config on a real Arch runs no sudo and
   lists only real differences.
3. A real apply on a matching machine prints nothing.
4. pytest, ruff and `dotfiles check` are green on every batch.

## Decisions

1. **One file per feature** (the user's choice). The file name is the
   gate, and a packages-only feature is four lines.
2. **An impossible combination fails in the feature** (`gaming` without
   multilib, a `swap` without a size), not in the config check. The
   config check knows keys and types, not features.
3. **The snapshot pair is part of `apply`** (`snapshot.pair`), not a
   feature: it must wrap the install, which runs before any feature.
4. **nvidia reads the GPU from sysfs and pci.ids**, so the driver is
   chosen on the first apply, without pciutils.
5. **The VS Code registry becomes `data/vscode.toml`**, like every other
   registry.

## Open Questions

1. The snapper hook stays a small `sh` script (pacman runs it as root,
   outside the tool). Or do you want it in Python, run by the system
   `python3`?
