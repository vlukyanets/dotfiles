#!/bin/bash
# Lock the screen, optionally turning off monitors afterward.
# Usage: lock-screen.sh [--monitors-off]

set -eu

~/.config/niri/switch-layout.sh 0

if [[ "${1:-}" == "--monitors-off" ]]; then
    noctalia msg session lock &
    sleep 0.3
    niri msg action power-off-monitors
else
    noctalia msg session lock
fi
