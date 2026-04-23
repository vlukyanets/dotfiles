#!/bin/bash
LID_STATE=$(cat /proc/acpi/button/lid/LID0/state | awk '{print $2}')

get_niri_user() {
    for pid in $(pgrep -x niri); do
        PROC_USER=$(ps -o user= -p "$pid")
        UID_NUM=$(id -u "$PROC_USER" 2>/dev/null) || continue
        WAYLAND_SOCK=$(ls /run/user/$UID_NUM/wayland-* 2>/dev/null | head -1)
        [ -n "$WAYLAND_SOCK" ] || continue
        echo "$PROC_USER $UID_NUM $WAYLAND_SOCK"
        return
    done
}

read REAL_USER UID_NUM WAYLAND_SOCK <<< $(get_niri_user)

if [ -z "$REAL_USER" ]; then
    logger "lid.sh: no active niri session found"
    exit 1
fi

XDG_RUNTIME_DIR="/run/user/$UID_NUM"
WAYLAND_DISPLAY=$(basename "$WAYLAND_SOCK")

ACTION=$( [ "$LID_STATE" = "closed" ] && echo "off" || echo "on" )

runuser -u "$REAL_USER" -- \
    env XDG_RUNTIME_DIR="$XDG_RUNTIME_DIR" \
        WAYLAND_DISPLAY="$WAYLAND_DISPLAY" \
        niri msg output eDP-1 "$ACTION"

logger "lid.sh: set eDP-1 $ACTION for user $REAL_USER"
