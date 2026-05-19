#!/bin/bash

get_systemd_user_env() { local v=$(systemctl --user show-environment | grep "^${1}=" | cut -d'=' -f2-); echo "${v:-${2:-}}"; }

PROFILE=$(get_systemd_user_env "POWER_PROFILE" "battery")
LOCK_CMD="qs -c noctalia-shell ipc call lockScreen lock"

log() { logger -t "swayidle-launch" "$*"; }

log "Starting swayidle with profile=${PROFILE}"

case "$PROFILE" in
    ac)
        exec swayidle -w \
            timeout 600  'brightnessctl -s set 30%' \
            resume       'brightnessctl -r' \
            timeout 1200 'niri msg action power-off-monitors' \
            resume       'niri msg action' \
            timeout 1500 "${LOCK_CMD}"
        ;;
    battery)
        exec swayidle -w \
            timeout 90   'brightnessctl -s set 10%' \
            resume       'brightnessctl -r' \
            timeout 180  'niri msg action power-off-monitors' \
            resume       'niri msg action' \
            timeout 300  "${LOCK_CMD}" \
            timeout 600  'systemctl sleep' \
            before-sleep "${LOCK_CMD}"
        ;;

    *)
        log "ERROR: unknown POWER_PROFILE='${PROFILE}' — falling back to battery"
        POWER_PROFILE=battery exec "$0"
        ;;
esac
