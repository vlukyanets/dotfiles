#!/usr/bin/env bash

set -euo pipefail

REPO="https://github.com/vlukyanets/dotfiles"

# ── git ───────────────────────────────────────────────────────────────────────
if ! command -v git &>/dev/null; then
    if command -v pacman &>/dev/null; then
        sudo pacman -S --needed --noconfirm git
    else
        echo "error: install git then re-run this script" >&2
        exit 1
    fi
fi

# ── openssh ───────────────────────────────────────────────────────────────────
if ! command -v ssh &>/dev/null; then
    if command -v pacman &>/dev/null; then
        sudo pacman -S --needed --noconfirm openssh
    else
        echo "error: install openssh then re-run this script" >&2
        exit 1
    fi
fi

# ── age / rage ────────────────────────────────────────────────────────────────
if ! command -v rage &>/dev/null && ! command -v age &>/dev/null; then
    if command -v pacman &>/dev/null; then
        sudo pacman -S --needed --noconfirm age
    else
        echo "error: install age or rage then re-run this script" >&2
        exit 1
    fi
fi

# ── chezmoi ───────────────────────────────────────────────────────────────────
if ! command -v chezmoi &>/dev/null; then
    if command -v pacman &>/dev/null; then
        sudo pacman -S --needed --noconfirm chezmoi
    else
        sh -c "$(curl -fsLS get.chezmoi.io)"
    fi
fi

# ── clone ─────────────────────────────────────────────────────────────────────
SOURCE="${XDG_DATA_HOME:-$HOME/.local/share}/chezmoi"
git clone "$REPO" "$SOURCE"

# ── hooks ─────────────────────────────────────────────────────────────────────
git -C "$SOURCE" config core.hooksPath .githooks

# ── decrypt ───────────────────────────────────────────────────────────────────
bash "$SOURCE/.githooks/post-checkout"

# ── apply ─────────────────────────────────────────────────────────────────────
pushd "$SOURCE" > /dev/null && chezmoi init --apply --source "$SOURCE"; popd > /dev/null
