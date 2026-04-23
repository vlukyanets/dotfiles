#!/bin/bash

PROFILE="${1:-battery}"
LOG_TAG="power-profile"

USER_ID=$(loginctl list-sessions --no-legend | awk '$3 != "root" {print $2}' | head -1)
USER_NAME=$(loginctl list-sessions --no-legend  | awk '$3 != "root" {print $3}' | head -1)
#USER_ID=$(id -u)
#USER_NAME=$(id -un)

if [[ -z "$USER_NAME" ]]; then
    logger -t "$LOG_TAG" "ERROR: could not resolve username for UID ${USER_ID} — aborting"
    exit 1
fi
RUNTIME_DIR="/run/user/${USER_ID}"

logger -t "$LOG_TAG" "profile=${PROFILE} user=${USER_NAME} uid=${USER_ID}"

run_as_user() {
    sudo -u "$USER_NAME" \
        XDG_RUNTIME_DIR="$RUNTIME_DIR" \
        WAYLAND_DISPLAY="wayland-1" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=${RUNTIME_DIR}/bus" \
        "$@"
}

set_user_env() {
    run_as_user systemctl --user set-environment "$1=$2"
}

set_cpu_governor() {
    local GOV="$1"
    local METHOD=""
    local CPU_COUNT
    CPU_COUNT=$(nproc --all 2>/dev/null || echo "?")

    if command -v cpupower &>/dev/null; then
        local OUTPUT
        OUTPUT=$(cpupower frequency-set -g "$GOV" 2>&1)
        local RC=$?
        if [[ $RC -eq 0 ]]; then
            METHOD="cpupower"
            local ACTUAL
            ACTUAL=$(cpupower frequency-info -p 2>/dev/null \
                | awk '/The governor/ {print $NF; exit}' \
                | tr -d '"')
            if [[ -n "$ACTUAL" ]]; then
                logger -t "$LOG_TAG" "CPU governor -> ${ACTUAL} (${CPU_COUNT} cores, ${METHOD})"
                [[ "$ACTUAL" != "$GOV" ]] && \
                    logger -t "$LOG_TAG" "WARN: requested '${GOV}' but kernel applied '${ACTUAL}'"
            else
                logger -t "$LOG_TAG" "CPU governor -> ${GOV} (${CPU_COUNT} cores, ${METHOD})"
            fi
        else
            logger -t "$LOG_TAG" "WARN: cpupower frequency-set -g ${GOV} failed (rc=${RC}): ${OUTPUT}"
            METHOD="failed"
        fi
    fi

    if [[ "$METHOD" == "failed" ]] || ! command -v cpupower &>/dev/null; then
        if command -v powerprofilesctl &>/dev/null; then
            local PPD_PROFILE
            case "$GOV" in
                performance)            PPD_PROFILE="performance" ;;
                powersave|conservative) PPD_PROFILE="power-saver" ;;
                *)                      PPD_PROFILE="balanced" ;;
            esac
            powerprofilesctl set "$PPD_PROFILE" 2>/dev/null \
                && logger -t "$LOG_TAG" "CPU governor -> ${GOV} via ppd profile '${PPD_PROFILE}'" \
                || logger -t "$LOG_TAG" "WARN: powerprofilesctl set ${PPD_PROFILE} failed"
            METHOD="ppd"
        fi
    fi

    if [[ -z "$METHOD" ]] || [[ "$METHOD" == "failed" ]]; then
        local SET_COUNT=0 FAIL_COUNT=0
        for GOV_PATH in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
            if echo "$GOV" > "$GOV_PATH" 2>/dev/null; then
                ((SET_COUNT++))
            else
                ((FAIL_COUNT++))
            fi
        done
        logger -t "$LOG_TAG" \
            "CPU governor -> ${GOV} via sysfs (${SET_COUNT} ok, ${FAIL_COUNT} failed)"
    fi
}

case "$PROFILE" in

    ac)
        logger -t "$LOG_TAG" "Applying AC profile"

        set_cpu_governor performance

        brightnessctl set 100% 2>/dev/null \
            && logger -t "$LOG_TAG" "Brightness -> 100%"

        set_user_env POWER_PROFILE ac
        run_as_user systemctl --user restart swayidle.service \
            && logger -t "$LOG_TAG" "swayidle restarted (ac config)"

        echo "ac" > /tmp/current-power-profile
        ;;

    battery)
        logger -t "$LOG_TAG" "Applying battery profile"

        set_cpu_governor powersave

        brightnessctl set 50% 2>/dev/null \
            && logger -t "$LOG_TAG" "Brightness -> 50%"

        set_user_env POWER_PROFILE battery
        run_as_user systemctl --user restart swayidle.service \
            && logger -t "$LOG_TAG" "swayidle restarted (battery config)"

        echo "battery" > /tmp/current-power-profile
        ;;

    *)
        logger -t "$LOG_TAG" "ERROR: unknown profile '${PROFILE}'"
        exit 1
        ;;
esac

logger -t "$LOG_TAG" "Done - profile=${PROFILE}"
exit 0
