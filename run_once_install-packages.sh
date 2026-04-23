#!/bin/bash
# Runs once on first chezmoi apply.
# Installs all packages on Arch Linux.

set -euo pipefail

# Only run on Arch Linux
if [ ! -f /etc/arch-release ]; then
    echo "Not Arch Linux, skipping package installation."
    exit 0
fi

# ── Helpers ───────────────────────────────────────────────────────────────────

# Resolve kernel packages based on hostname.
#   hyper-lin  — personal laptop → linux-zen (low-latency, gaming/desktop)
#   *-server   — any server      → linux-lts (long-term stable)
#   (default)                    → linux     (vanilla stable)
resolve_kernel() {
    local host
    host=$(cat /etc/hostname 2>/dev/null || echo "unknown")
    case "$host" in
        hyper-lin)
            KERNEL_PKGS=("linux-zen" "linux-zen-headers")
            ;;
        *-server|*server*)
            KERNEL_PKGS=("linux-lts" "linux-lts-headers")
            ;;
        *)
            KERNEL_PKGS=("linux" "linux-headers")
            ;;
    esac
    echo "  Hostname: ${host} → kernel: ${KERNEL_PKGS[*]}" >&2
}

# Detect NVIDIA GPU generation and set NVIDIA_DRIVER / NVIDIA_LIB32.
detect_nvidia_driver() {
    local gpu
    gpu=$(lspci 2>/dev/null | grep -iE 'vga|3d controller|display controller' | grep -i nvidia | head -1)

    if [ -z "$gpu" ]; then
        echo "  No NVIDIA GPU detected, skipping driver selection." >&2
        NVIDIA_DRIVER=""
        NVIDIA_LIB32=""
        return
    fi

    echo "  Detected GPU: $gpu" >&2

    # Modern: RTX (20xx/30xx/40xx/50xx), GTX 16xx (Turing), MX 3xx/4xx/5xx+ (Turing/Ampere)
    if echo "$gpu" | grep -qiE 'RTX [2-9][0-9]{3}|GTX 16[0-9]{2}|MX[3-9][0-9]{2}'; then
        NVIDIA_DRIVER="nvidia-dkms"
        NVIDIA_LIB32="lib32-nvidia-utils"

    # Pascal (GTX 10xx) / Maxwell (GTX 9xx) — 580xx legacy
    # MX 1xx/2xx (Maxwell/Pascal mobile), xxxMX (920MX/930MX/940MX, Maxwell mobile)
    elif echo "$gpu" | grep -qiE 'GTX 10[0-9]{2}|GTX 9[0-9]{2}|MX[12][0-9]{2}|[0-9]{3}MX'; then
        NVIDIA_DRIVER="nvidia-580xx-dkms"
        NVIDIA_LIB32="lib32-nvidia-580xx-utils"

    # Kepler (GTX 600/700) — 470xx legacy
    elif echo "$gpu" | grep -qiE 'GTX [67][0-9]{2}'; then
        NVIDIA_DRIVER="nvidia-470xx-dkms"
        NVIDIA_LIB32="lib32-nvidia-470xx-utils"

    # Fermi (GTX 400/500) — 390xx legacy
    elif echo "$gpu" | grep -qiE 'GTX [45][0-9]{2}'; then
        NVIDIA_DRIVER="nvidia-390xx-dkms"
        NVIDIA_LIB32="lib32-nvidia-390xx-utils"

    # Tesla/Curie (GeForce 8/9/100/200/300) — 340xx legacy, no lib32
    elif echo "$gpu" | grep -qiE 'GeForce [89][0-9]{2}|GeForce [123][0-9]{2}'; then
        NVIDIA_DRIVER="nvidia-340xx-dkms"
        NVIDIA_LIB32=""

    # Unknown/future — fall back to current driver
    else
        echo "  WARNING: unrecognised NVIDIA GPU generation, falling back to nvidia-dkms." >&2
        NVIDIA_DRIVER="nvidia-dkms"
        NVIDIA_LIB32="lib32-nvidia-utils"
    fi

    echo "  Selected driver: ${NVIDIA_DRIVER} ${NVIDIA_LIB32}" >&2
}

# ── 1. Bootstrap: git, base-devel, rustup ─────────────────────────────────────
echo "==> [1/9] Bootstrap (git, base-devel, rustup)..."
sudo pacman -Syu --needed --noconfirm git base base-devel rustup

# ── 2. Rust toolchain ─────────────────────────────────────────────────────────
echo "==> [2/9] Rust stable toolchain..."
rustup default stable

# ── 3. Install paru ───────────────────────────────────────────────────────────
echo "==> [3/9] paru (AUR helper)..."
if ! command -v paru &>/dev/null; then
    tmp=$(mktemp -d)
    git clone https://aur.archlinux.org/paru.git "$tmp/paru"
    pushd "$tmp/paru"
    makepkg -si --noconfirm
    popd
    rm -rf "$tmp"
else
    echo "  paru already installed, skipping."
fi

# ── 4. NVIDIA drivers (conditional) ──────────────────────────────────────────
echo "==> [4/9] NVIDIA drivers..."
NVIDIA_DRIVER=""
NVIDIA_LIB32=""
detect_nvidia_driver

if [ -n "$NVIDIA_DRIVER" ]; then
    NVIDIA_PKGS=("$NVIDIA_DRIVER")
    [ -n "$NVIDIA_LIB32" ] && NVIDIA_PKGS+=("$NVIDIA_LIB32")
    paru -S --needed --noconfirm "${NVIDIA_PKGS[@]}"
else
    echo "  No NVIDIA GPU — skipping."
fi

# ── 5. Base packages ──────────────────────────────────────────────────────────
echo "==> [5/9] Base packages..."
KERNEL_PKGS=()
resolve_kernel

paru -S --needed --noconfirm \
    acpid \
    base \
    base-devel \
    bat \
    bluez \
    bluez-utils \
    brightnessctl \
    btrfs-progs \
    chezmoi \
    cpupower \
    cryptsetup \
    curl \
    dkms \
    dnsmasq \
    duf \
    efitools \
    eza \
    fastfetch \
    fd \
    fzf \
    htop \
    intel-ucode \
    jq \
    just \
    less \
    linux-firmware \
    lvm2 \
    nano \
    ncdu \
    networkmanager \
    openssh \
    reflector \
    ripgrep \
    rsync \
    sbctl \
    snap-pac \
    snapper \
    swtpm \
    systemd-ukify \
    terminus-font \
    tpm2-tools \
    tree \
    unzip \
    usbutils \
    wget \
    wl-clipboard \
    yazi \
    yq \
    zip \
    zsh \
    "${KERNEL_PKGS[@]}"

# ── 6. Programming languages ──────────────────────────────────────────────────
echo "==> [6/9] Programming languages..."
paru -S --needed --noconfirm \
    clang \
    cmake \
    dotnet-sdk \
    gdb \
    gcc \
    go \
    lldb \
    meson \
    ninja \
    nodejs \
    npm \
    python-pip \
    rustup

# ── 7. Desktop environment ────────────────────────────────────────────────────
echo "==> [7/10] Desktop environment..."
paru -S --needed --noconfirm \
    cava \
    discord \
    edk2-ovmf \
    evince \
    fcitx5 \
    fcitx5-chinese-addons \
    fcitx5-gtk \
    fcitx5-material-color \
    fcitx5-pinyin-zhwiki \
    firefox \
    gnome-themes-extra \
    greetd \
    greetd-tuigreet \
    kitty \
    libvirt \
    niri \
    noctalia-shell \
    pipewire \
    pipewire-alsa \
    pipewire-jack \
    pipewire-pulse \
    plymouth \
    plymouth-theme-arch-logo-new \
    power-profiles-daemon \
    qbittorrent \
    qt5-base \
    qt5-graphicaleffects \
    qt6-5compat \
    rbw \
    swayidle \
    swaylock \
    tailscale \
    telegram-desktop \
    termusic \
    veracrypt \
    virt-manager \
    wireplumber \
    xdg-desktop-portal-gtk \
    xdg-desktop-portal-wlr \
    xdg-utils \
    xwayland-satellite \
    zoom

# ── 8. Fonts ──────────────────────────────────────────────────────────────────
echo "==> [8/10] Fonts..."
paru -S --needed --noconfirm \
    noto-fonts-cjk \
    noto-fonts-emoji \
    otf-atkinsonhyperlegiblemono-nerd \
    otf-aurulent-nerd \
    otf-codenewroman-nerd \
    otf-comicshanns-nerd \
    otf-commit-mono-nerd \
    otf-droid-nerd \
    otf-firamono-nerd \
    otf-geist-mono-nerd \
    otf-hasklig-nerd \
    otf-hermit-nerd \
    otf-monaspace-nerd \
    otf-opendyslexic-nerd \
    otf-overpass-nerd \
    ttf-0xproto-nerd \
    ttf-3270-nerd \
    ttf-adwaitamono-nerd \
    ttf-agave-nerd \
    ttf-anonymouspro-nerd \
    ttf-arimo-nerd \
    ttf-bigblueterminal-nerd \
    ttf-bitstream-vera-mono-nerd \
    ttf-cascadia-code-nerd \
    ttf-cascadia-mono-nerd \
    ttf-cousine-nerd \
    ttf-d2coding-nerd \
    ttf-daddytime-mono-nerd \
    ttf-dejavu-nerd \
    ttf-envycoder-nerd \
    ttf-fantasque-nerd \
    ttf-firacode-nerd \
    ttf-go-nerd \
    ttf-gohu-nerd \
    ttf-hack-nerd \
    ttf-heavydata-nerd \
    ttf-iawriter-nerd \
    ttf-ibmplex-mono-nerd \
    ttf-inconsolata-go-nerd \
    ttf-inconsolata-lgc-nerd \
    ttf-inconsolata-nerd \
    ttf-intone-nerd \
    ttf-iosevka-nerd \
    ttf-iosevkaterm-nerd \
    ttf-iosevkatermslab-nerd \
    ttf-jetbrains-mono-nerd \
    ttf-lekton-nerd \
    ttf-liberation-mono-nerd \
    ttf-lilex-nerd \
    ttf-martian-mono-nerd \
    ttf-meslo-nerd \
    ttf-monofur-nerd \
    ttf-monoid-nerd \
    ttf-mononoki-nerd \
    ttf-mplus-nerd \
    ttf-nerd-fonts-symbols \
    ttf-nerd-fonts-symbols-mono \
    ttf-noto-nerd \
    ttf-profont-nerd \
    ttf-proggyclean-nerd \
    ttf-recursive-nerd \
    ttf-roboto-mono-nerd \
    ttf-sarasa-gothic \
    ttf-sharetech-mono-nerd \
    ttf-sourcecodepro-nerd \
    ttf-space-mono-nerd \
    ttf-terminus-nerd \
    ttf-tinos-nerd \
    ttf-ubuntu-mono-nerd \
    ttf-ubuntu-nerd \
    ttf-victor-mono-nerd \
    ttf-zed-mono-nerd

# ── 9. IDEs & productivity tools ──────────────────────────────────────────────
echo "==> [9/10] IDEs & productivity tools..."
paru -S --needed --noconfirm \
    claude-desktop-bin \
    lmstudio-bin \
    obsidian \
    onlyoffice-bin \
    qemu-desktop \
    visual-studio-code-bin

# ── 10. Clean package cache ───────────────────────────────────────────────────
echo "==> [10/10] Cleaning package cache..."
paru -Scc --noconfirm

echo "==> Done."
