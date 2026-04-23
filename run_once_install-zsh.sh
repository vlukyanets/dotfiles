#!/bin/bash
# Runs once on first chezmoi apply.
# Installs oh-my-zsh with Powerlevel10k theme and custom plugins.
# Runs after chezmoi has already placed ~/.zshrc, so KEEP_ZSHRC=yes is set
# to prevent the oh-my-zsh installer from overwriting it.

set -euo pipefail

ZSH_DIR="${HOME}/.oh-my-zsh"
CUSTOM_DIR="${ZSH_DIR}/custom"

# ── oh-my-zsh ─────────────────────────────────────────────────────────────────
if [ -d "$ZSH_DIR" ]; then
    echo "==> oh-my-zsh already installed, skipping."
else
    echo "==> Installing oh-my-zsh..."
    KEEP_ZSHRC=yes sh -c "$(curl -fsSL https://raw.githubusercontent.com/ohmyzsh/ohmyzsh/master/tools/install.sh)" "" --unattended
fi

# ── Theme: Powerlevel10k ──────────────────────────────────────────────────────
P10K_DIR="${CUSTOM_DIR}/themes/powerlevel10k"
if [ -d "$P10K_DIR" ]; then
    echo "==> Powerlevel10k already installed, updating..."
    git -C "$P10K_DIR" pull --ff-only
else
    echo "==> Installing Powerlevel10k theme..."
    git clone --depth=1 https://github.com/romkatv/powerlevel10k.git "$P10K_DIR"
fi

# ── Plugin: zsh-autosuggestions ───────────────────────────────────────────────
ZSH_AUTOSUGGEST_DIR="${CUSTOM_DIR}/plugins/zsh-autosuggestions"
if [ -d "$ZSH_AUTOSUGGEST_DIR" ]; then
    echo "==> zsh-autosuggestions already installed, updating..."
    git -C "$ZSH_AUTOSUGGEST_DIR" pull --ff-only
else
    echo "==> Installing zsh-autosuggestions..."
    git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions.git "$ZSH_AUTOSUGGEST_DIR"
fi

# ── Plugin: zsh-syntax-highlighting ──────────────────────────────────────────
ZSH_SYNTAX_DIR="${CUSTOM_DIR}/plugins/zsh-syntax-highlighting"
if [ -d "$ZSH_SYNTAX_DIR" ]; then
    echo "==> zsh-syntax-highlighting already installed, updating..."
    git -C "$ZSH_SYNTAX_DIR" pull --ff-only
else
    echo "==> Installing zsh-syntax-highlighting..."
    git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting.git "$ZSH_SYNTAX_DIR"
fi

echo "==> Done."
