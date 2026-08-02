# dotfiles (chezmoi)

Modular chezmoi dotfiles targeting Arch Linux. Supports multiple hosts with per-host feature flags, age-encrypted secrets, and automatic mirror/driver selection.

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| `curl` | Download bootstrap script | `sudo pacman -S curl` |
| `git` | Clone repo, run hooks | `sudo pacman -S git` |
| `chezmoi` | Apply dotfiles | see Bootstrap below |

## Install scripts

Scripts run in order on first `chezmoi apply`. All are `run_once_` — they re-run only if their content changes (which happens automatically when the package list or any rendered template value changes).

| Script | Condition | What it does |
|---|---|---|
| `00-configure-pacman` | always | Sets `ParallelDownloads`; enables `[multilib]` if configured |
| `01-install-base-packages` | always | Installs essential system packages via pacman |
| `02-install-reflector` | always | Installs reflector; writes `/etc/xdg/reflector/reflector.conf` from host data; enables daily timer |
| `03-install-system-config` | always | Installs `terminus-font`; deploys `/etc/modprobe.d/`, `/etc/ssh/sshd_config`, `locale.conf`, `locale.gen` (runs `locale-gen`), `vconsole.conf` |
| `04-install-paru` | `paru` | Installs rustup (pacman) then builds paru from AUR; sets `MAKEFLAGS=-j$(nproc)` |
| `05-install-nvidia` | `nvidia` | Detects GPU generation via `lspci`; installs matching DKMS driver + kernel headers + lib32 |
| `06-install-zsh` | `zsh` | Installs zsh, oh-my-zsh, powerlevel10k, autosuggestions, syntax-highlighting; sets default shell |
| `07-install-base-tools` | `base_tools_enabled` | `curl wget fzf htop iotop jq yq rsync tree tmux unzip zip 7zip` |
| `08-install-advanced-tools` | `advanced_tools_enabled` | `fd ncdu duf btop zellij neovim fastfetch ripgrep zoxide yazi` |
| `09-install-niri` | `niri_enabled` | Niri compositor, `brightnessctl`, greetd/tuigreet, fonts, `wl-clipboard`; deploys greetd system config |
| `10-install-noctalia-shell` | `niri_enabled` + `paru` | Installs noctalia-shell, pipewire-jack, qt6-multimedia-ffmpeg from AUR |
| `11-install-pipewire` | always | Installs PipeWire stack; enables pipewire, pipewire-pulse, wireplumber user services |
| `12-install-desktop-programs` | `niri_enabled` | GUI apps via pacman + AUR (see below) |
| `13-install-rbw` | `rbw_enabled` | Installs `rbw` + `pinentry` (Bitwarden CLI) |
| `14-install-libvirt` | `libvirt_enabled` | QEMU/KVM stack; enables libvirtd; adds user to `libvirt` and `kvm` groups |
| `15-install-dev-tools` | `dev_tools_enabled` | Full dev toolchain; `visual-studio-code-bin` via paru if enabled |
| `16-install-docker` | always | Installs `docker`, `docker-buildx`, `docker-compose`; enables docker service; adds user to `docker` group |
| `17-configure-dark-theme` | `niri_enabled` | Installs Adwaita-dark; applies via `gsettings` |
| `18-install-ai-clients` | `ai.clients.*` | Installs enabled AI clients from AUR via paru |
| `19-install-yubikey` | `yubikey_enabled` | Installs `yubikey-manager`, `libfido2`, `ccid`, `pcsclite`, `usbutils`; enables `pcscd.socket`; deploys `70-u2f.rules`; deploys `yubikey-next-id.sh` script to `/usr/local/bin/` |
| `20-install-plymouth` | always | Installs Plymouth; uses `plymouth-theme-arch-logo-new` (AUR, requires paru) or `bgrt` fallback; inserts `plymouth` hook into `/etc/mkinitcpio.conf`; rebuilds initramfs |
| `21-install-tailscale` | `tailscale_enabled` | Installs `tailscale`; enables `tailscaled.service`; sets current user as operator |
| `22-install-fcitx5` | `niri_enabled` + `use_fcitx5` | Installs `fcitx5 fcitx5-chinese-addons fcitx5-gtk fcitx5-qt fcitx5-configtool` |
| `after_23-update-fcitx5-profile` | `use_fcitx5` | `run_onchange` — rewrites `~/.config/fcitx5/profile` from `languages` list; restarts fcitx5 |
| `24-install-winpodx` | `winpodx_enabled` + `paru` | Installs `winpodx` |

### Desktop programs (script 12)

| Source | Packages |
|---|---|
| pacman | `kitty` `firefox` `discord` `telegram-desktop` `evince` `qbittorrent` `cava` `cmatrix` `obsidian` `termusic` `doublecmd-qt6` `veracrypt` `vlc` `mission-center` |
| AUR (paru) | `onlyoffice-bin` `zoom` `clock-rs-git` |

### Development tools (script 15)

| Source | Packages |
|---|---|
| pacman | `base-devel` `gcc` `clang` `gdb` `lldb` `llvm` `python` `python-pip` `nodejs` `npm` `rustup` `dotnet-sdk` `go` `ninja` `meson` `cmake` `just` |
| AUR (paru) | `visual-studio-code-bin` |

### AI clients (script 18)

| Source | Packages |
|---|---|
| AUR (paru) | `claude-desktop-bin` `claude-code` |

## Host feature flags

Flags are set per-host in `.chezmoidata.toml`. Unknown hosts are prompted interactively.

### Top-level flags

| Flag | Type | Default | Effect |
|---|---|---|---|
| `paru_enabled` | bool | `false` | Build and install paru AUR helper |
| `nvidia_enabled` | bool | `false` | Auto-detect and install NVIDIA DKMS driver |
| `zsh_enabled` | bool | `false` | Install zsh + oh-my-zsh + powerlevel10k |
| `base_tools_enabled` | bool | `false` | Install base CLI toolkit |
| `advanced_tools_enabled` | bool | `false` | Install advanced CLI toolkit |
| `niri_enabled` | bool | `false` | Install niri desktop environment and all desktop scripts |
| `libvirt_enabled` | bool | `false` | Install QEMU/KVM virtualisation stack |
| `dev_tools_enabled` | bool | `false` | Install development toolchain |
| `rbw_enabled` | bool | `false` | Install rbw Bitwarden CLI + pinentry |
| `yubikey_enabled` | bool | `false` | Install YubiKey tools, enable `pcscd.socket`, deploy U2F udev rules |
| `tailscale_enabled` | bool | `false` | Install Tailscale, enable `tailscaled.service`, set user as operator |
| `winpodx_enabled` | bool | `false` | Installs WinPodX |
| `use_fcitx5` | bool | `false` | Install fcitx5 input method framework and configure profile |
| `languages` | array | `[]` | Input methods to configure in fcitx5 (`english`, `russian`, `ukrainian`, `chinese`) |

### `[hostname.pacman]`

| Flag | Type | Default | Effect |
|---|---|---|---|
| `multilib_enabled` | bool | `false` | Enable pacman `[multilib]` repository |
| `parallel` | int | `1` | `ParallelDownloads` value in `pacman.conf` |

### `[hostname.reflector]`

| Flag | Type | Default | Effect |
|---|---|---|---|
| `countries` | string | `""` | Comma-separated country list (empty = no filter) |
| `sort` | string | `"age"` | Sort method: `age`, `rate`, `country`, `score`, `delay` |
| `servers` | int | `5` | Number of mirrors to select (`--latest`) |

### `[hostname.ai.clients]`

| Flag | Type | Default | Effect |
|---|---|---|---|
| `claude_desktop` | bool | `false` | Install Claude desktop client (GUI) |
| `claude_code` | bool | `false` | Install Claude Code (CLI) |

## Base packages

Always installed regardless of host:

`base` `base-devel` `btrfs-progs` `cryptsetup` `intel-ucode` `linux-firmware`
`sbctl` `systemd-ukify` `curl` `wget` `networkmanager` `openssh` `nano` `vim` `less`

## GPU driver selection

Detection uses `lspci` model name matching. Kernel headers are auto-detected from `uname -r`.

| GPU generation | Examples | Driver | lib32 |
|---|---|---|---|
| Turing / Ampere / Ada+ (RTX 20xx+, GTX 16xx) | RTX 3070, GTX 1660 | `nvidia-dkms` | `lib32-nvidia-utils` |
| Pascal / Maxwell (GTX 10xx, GTX 9xx, MX 1–2xx) | GTX 1080, GTX 970 | `nvidia-580xx-dkms` | `lib32-nvidia-580xx-utils` |
| Kepler (GTX 600/700) | GTX 780, GTX 660 | `nvidia-470xx-dkms` | `lib32-nvidia-470xx-utils` |
| Fermi (GTX 400/500) | GTX 580, GTX 460 | `nvidia-390xx-dkms` | `lib32-nvidia-390xx-utils` |
| Tesla / Curie (GeForce 8/9/100–300) | 9800 GT, 8600 GT | `nvidia-340xx-dkms` | — |

Legacy drivers (anything except `nvidia-dkms`) are AUR packages and require `paru = true`.

