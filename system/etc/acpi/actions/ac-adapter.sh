#!/usr/bin/env bash
status=$(cat /sys/class/power_supply/AC/online 2>/dev/null || echo 1)
if [[ "$status" == "1" ]]; then
    powerprofilesctl set balanced
else
    powerprofilesctl set power-saver
fi
