#!/bin/bash
FLAG="/tmp/swayidle-dimmed-${UID}"

if [[ -f "$FLAG" ]]; then
    rm -f "$FLAG"
    brightnessctl -r
fi

niri msg action power-on-monitors
