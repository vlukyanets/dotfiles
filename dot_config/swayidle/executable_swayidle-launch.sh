#!/bin/bash
H="${HOME}/.config/swayidle"

log() { logger -t "swayidle" "$*"; }
log "Starting swayidle (power-saver/balanced timeouts; performance = no idle)"

exec swayidle -w \
    timeout 90   "$H/on-idle.sh dim      power-saver" \
    timeout 120  "$H/on-idle.sh lock     power-saver" \
    timeout 180  "$H/on-idle.sh dpms-off power-saver" \
    timeout 240  "$H/on-idle.sh dim      balanced" \
    timeout 300  "$H/on-idle.sh lock     balanced" \
    timeout 600  "$H/on-idle.sh dpms-off balanced" \
    resume       "$H/on-resume.sh" \
    before-sleep "${HOME}/.config/swaylock/lock.sh"
