#!/bin/bash

LOCK_PIDFILE="/tmp/swaylock-${USER}.pid"

# ---- Guard: don't start a second instance -----------------------------------
if [[ -f "$LOCK_PIDFILE" ]]; then
    PID=$(cat "$LOCK_PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        exit 0   # already locked
    fi
    rm -f "$LOCK_PIDFILE"
fi

# ---- Optional: notify before locking (comment out if not using mako/dunst) --
# notify-send -u low -t 2000 "Locking screen..."

# ---- Lock -------------------------------------------------------------------
swaylock --config "${HOME}/.config/swaylock/config" &
LOCK_PID=$!
echo "$LOCK_PID" > "$LOCK_PIDFILE"

# ---- Clean up pidfile when swaylock exits -----------------------------------
wait "$LOCK_PID"
rm -f "$LOCK_PIDFILE"
