#!/usr/bin/env bash

declare -A LAYOUT_MAP
LAYOUT_MAP["English (US)"]="keyboard-us"
LAYOUT_MAP["Russian"]="keyboard-ru"
LAYOUT_MAP["Ukrainian"]="keyboard-ua"
LAYOUT_MAP["Chinese"]="pinyin"

niri msg action switch-layout next

active_name=$(niri msg keyboard-layouts | grep '\*' | cut -d' ' -f4-)

echo "Active name: $active_name"
fcitx5_im="${LAYOUT_MAP[$active_name]}"

if [ -z "$fcitx5_im" ]; then
    echo "Warning: no fcitx5 mapping for layout '$active_name'" >&2
    fcitx5-remote -s keyboard-us
else
    fcitx5-remote -s "$fcitx5_im"
fi

