# dotfiles

Personal dotfiles for Arch Linux managed with [chezmoi](https://chezmoi.io).

## Stack

| Category | Tool |
|---|---|
| Compositor | [niri](https://github.com/YaLTeR/niri) |
| Shell | zsh + Powerlevel10k |
| Terminal | kitty |
| Bar / Shell UI | noctalia-shell |
| Audio | PipeWire + WirePlumber |
| Input method | fcitx5 (English + Pinyin) |
| Screen lock | swaylock |
| Idle daemon | swayidle |
| Password manager | rbw (Bitwarden CLI) |
| Boot splash | Plymouth (`arch-logo-new` theme) |

## Repository structure

```
dotfiles/
├── dot_*                        # ~/.* files (gitconfig, zshrc, p10k.zsh, gtkrc-2.0, …)
├── private_dot_config/          # ~/.config/* directories
│   ├── niri/                    # Wayland compositor config
│   ├── swayidle/                # Idle management
│   ├── swaylock/                # Screen lock
│   ├── fcitx5/                  # Input method
│   ├── pipewire/                # Audio
│   ├── wireplumber/             # Audio session manager
│   ├── kitty/                   # Terminal
│   ├── noctalia/                # Shell/bar
│   ├── rbw/                     # Bitwarden CLI
│   ├── termusic/                # Music player
│   ├── gtk-3.0/                 # GTK3 theme
│   ├── systemd/user/            # User systemd services
│   ├── qBittorrent/             # BitTorrent client
│   ├── VeraCrypt/               # Disk encryption
│   └── …
├── system/                      # Root-owned system files (deployed via system/install.sh)
│   ├── install.sh               # Deploy script (run as root)
│   ├── etc/
│   │   ├── acpi/                # Lid switch handler
│   │   ├── udev/rules.d/        # Power profile udev rules
│   │   ├── mkinitcpio.conf
│   │   ├── mkinitcpio.d/        # Kernel presets (zen / lts / vanilla)
│   │   ├── pacman.conf
│   │   ├── makepkg.conf
│   │   ├── plymouth/            # Boot splash config
│   │   ├── locale.gen / locale.conf / vconsole.conf
│   │   ├── ssh/sshd_config
│   │   └── xdg/reflector/       # Mirror refresh config
│   └── usr/local/bin/
│       └── power-profile-switch # AC/battery profile switcher
├── run_once_install-packages.sh # First-run package installer
└── run_once_install-zsh.sh      # First-run oh-my-zsh + plugins installer
```

## First-time setup

### Prerequisites

- Fresh Arch Linux installation
- `chezmoi` installed (`pacman -S chezmoi`)

### Apply dotfiles

Clone the repo and initialise chezmoi pointing at it:

```bash
chezmoi init <username>/<repo>
chezmoi apply
```

Both `run_once_` scripts run automatically on the first `chezmoi apply` and are skipped on subsequent runs:

- `run_once_install-packages.sh` — installs all system packages via pacman + paru
- `run_once_install-zsh.sh` — installs oh-my-zsh, Powerlevel10k theme, `zsh-autosuggestions`, and `zsh-syntax-highlighting`

`KEEP_ZSHRC=yes` is set during oh-my-zsh installation so it does not overwrite the `~/.zshrc` already placed by chezmoi.

### Deploy system files

```bash
cd "<dotfiles>"
sudo system/install.sh
```

This copies all files under `system/` to their target paths, sets correct permissions and ownership, decrypts and restores Secure Boot keys, and reloads udev rules.

The kernel preset installed (`linux-zen`, `linux-lts`, or `linux`) is chosen automatically based on the running kernel.

## Package installation stages

| Stage | Content |
|---|---|
| 1 | Bootstrap: `git`, `base-devel`, `rustup` |
| 2 | Rust stable toolchain |
| 3 | paru (AUR helper, built from source) |
| 4 | NVIDIA driver — auto-detected by GPU generation |
| 5 | Base system packages + kernel (hostname-dependent) |
| 6 | Programming languages |
| 7 | Desktop environment |
| 8 | Fonts |
| 9 | IDEs & productivity tools |
| 10 | Package cache cleanup |

### Kernel selection by hostname

| Hostname | Kernel |
|---|---|
| `*server*` | `linux-lts` |
| laptop | `linux-zen` |
| anything else | `linux` |

### NVIDIA driver selection

| GPU generation | Package |
|---|---|
| RTX 20xx+ / GTX 16xx / MX 3xx–5xx+ (Turing/Ampere) | `nvidia-dkms` |
| GTX 10xx / GTX 9xx / MX 1xx–2xx / 9x0MX (Pascal/Maxwell) | `nvidia-580xx-dkms` |
| GTX 6xx / GTX 7xx (Kepler) | `nvidia-470xx-dkms` |
| GTX 4xx / GTX 5xx (Fermi) | `nvidia-390xx-dkms` |
| GeForce 8/9/100/200/300 (Tesla) | `nvidia-340xx-dkms` |

## Power management

AC plug/unplug events trigger `/usr/local/bin/power-profile-switch` via udev, which:
- Sets the CPU governor (`performance` on AC, `powersave` on battery)
- Adjusts screen brightness
- Restarts `swayidle` with the appropriate timeout profile

On login, `power-profile-init.service` seeds `POWER_PROFILE` in the systemd user environment before `swayidle.service` starts, so the correct idle profile is active from the first second.
