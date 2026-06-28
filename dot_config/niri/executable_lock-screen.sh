#!/bin/bash
# Lock the screen, optionally turning off monitors afterward.
# Usage: lock-screen.sh [--monitors-off]

~/.config/niri/switch-layout.sh 0

if [[ "$1" == "--monitors-off" ]]; then
    qs -c noctalia-shell ipc call lockScreen lock &
    sleep 0.3
    niri msg action power-off-monitors
else
    qs -c noctalia-shell ipc call lockScreen lock
fi
