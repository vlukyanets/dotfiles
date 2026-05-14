#!/bin/bash
# Usage: on-idle.sh <action> <required-profile>
ACTION="$1"
REQUIRED_PROFILE="$2"
FLAG="/tmp/swayidle-dimmed-${UID}"

[ "$(powerprofilesctl get)" = "$REQUIRED_PROFILE" ] || exit 0

case "$ACTION" in
    dim)
        brightnessctl -s set "$([ "$REQUIRED_PROFILE" = power-saver ] && echo 10% || echo 30%)"
        touch "$FLAG"
        ;;
    lock)
        "${HOME}/.config/swaylock/lock.sh"
        ;;
    dpms-off)
        niri msg action power-off-monitors
        ;;
esac
