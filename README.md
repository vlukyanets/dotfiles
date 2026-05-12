# dotfiles (chezmoi)

Minimal chezmoi dotfiles targeting Arch Linux.

## Prerequisites

| Tool | Purpose | Install |
|---|---|---|
| `curl` | Download bootstrap script | `sudo pacman -S curl` |
| `git` | Clone repo, run hooks | `sudo pacman -S git` |
| `openssh` | SSH key pair used as age identity | `sudo pacman -S openssh` |
| `age` | Encrypt / decrypt `.age` files | `sudo pacman -S age` |
| `chezmoi` | Apply dotfiles | see Bootstrap below |

An SSH key pair must exist before running bootstrap (`ssh-keygen -t ed25519` if not).

Two environment variables control encryption behaviour:

| Variable | Default | Purpose |
|---|---|---|
| `AGE_CMD` | `age` | age-compatible binary to use (`rage`, etc.) |
| `AGE_IDENTITY` | chezmoi config → `~/.ssh/id_ed25519` | SSH private key used for decryption |

## Bootstrap

```sh
bash <(curl -fsLS https://raw.githubusercontent.com/vlukyanets/dotfiles/main/bootstrap.sh)
```

The script installs missing prerequisites (`age`, `chezmoi`), clones the repo, decrypts age-encrypted files, and runs `chezmoi apply`. Known hostnames are configured automatically; unknown machines are prompted for each feature flag.

After the first apply, git hooks are active — encrypted files decrypt on checkout and re-encrypt before commit automatically.

## Install scripts

Scripts run in order on first `chezmoi apply`:

| Script | Condition | What it does |
|---|---|---|
| `run_once_00-configure-pacman` | always | Sets `ParallelDownloads` (host-configured); enables `[multilib]` repo if enabled |
| `run_once_01-install-base-packages` | always | Installs essential system packages via pacman |
| `run_once_02-install-paru` | `paru` | Installs rustup (pacman) then builds paru from AUR |
| `run_once_03-install-nvidia` | `nvidia` | Detects GPU, installs matching DKMS driver + lib32 |

## Host feature flags

| Flag | Type | Effect |
|---|---|---|
| `paru` | bool | Install rustup + paru AUR helper |
| `nvidia` | bool | Install NVIDIA DKMS driver and lib32 utils |
| `pacman.multilib_enabled` | bool | Enable pacman `[multilib]` repository |
| `pacman.parallel` | int | `ParallelDownloads` value in `pacman.conf` (default: `1`) |

## Base packages

Always installed regardless of host:

`base` `base-devel` `btrfs-progs` `cryptsetup` `intel-ucode` `linux-firmware`
`sbctl` `systemd-ukify` `curl` `wget` `networkmanager` `openssh` `nano` `vim` `less`

## GPU driver selection

Detection uses `lspci` model name matching:

| GPU generation | Examples | Driver | lib32 |
|---|---|---|---|
| Turing / Ampere / Ada / Blackwell (RTX 20xx+, GTX 16xx) | RTX 3070, GTX 1660 | `nvidia-dkms` | `lib32-nvidia-utils` |
| Pascal / Maxwell (GTX 10xx, GTX 9xx, MX 1xx/2xx) | GTX 1080, GTX 970 | `nvidia-580xx-dkms` | `lib32-nvidia-580xx-utils` |
| Kepler (GTX 600/700) | GTX 780, GTX 660 | `nvidia-470xx-dkms` | `lib32-nvidia-470xx-utils` |
| Fermi (GTX 400/500) | GTX 580, GTX 460 | `nvidia-390xx-dkms` | `lib32-nvidia-390xx-utils` |
| Tesla / Curie (GeForce 8/9/100–300) | 9800 GT, 8600 GT | `nvidia-340xx-dkms` | — |

Legacy drivers (anything other than `nvidia-dkms`) are AUR packages and require `paru = true`.

Kernel headers are auto-detected from `uname -r` (`linux`, `linux-lts`, `linux-zen`, `linux-hardened`).

## Adding a new host

Decrypt `hosts.toml.age`, add the entry, re-encrypt, and commit:

```sh
rage -d -i ~/.ssh/id_ed25519 -o hosts.toml hosts.toml.age
# edit hosts.toml — add entry, e.g.:
# [new-machine]
# paru   = true
# nvidia = false
# [new-machine.pacman]
# multilib_enabled = true
# parallel         = 5
rage -R .age-recipients -o hosts.toml.age hosts.toml
git add hosts.toml.age && git commit
```

Any `pacman` key omitted by a host falls back to its default (`multilib_enabled = false`, `parallel = 1`).

## Managing encryption recipients

All SSH public keys authorised to decrypt files are listed in `.age-recipients`. To add a new key:

```sh
echo "ssh-ed25519 AAAA... # new-machine" >> .age-recipients
# re-encrypt all age files with the updated recipients list
for f in *.age; do
    plain="${f%.age}"
    rage -d -i ~/.ssh/id_ed25519 -o "$plain" "$f"
    rage -R .age-recipients -o "$f" "$plain"
    rm "$plain"
done
git add .age-recipients *.age && git commit
```
