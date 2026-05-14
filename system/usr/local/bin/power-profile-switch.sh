#!/usr/bin/env bash
profiles=(balanced power-saver performance)
current=$(powerprofilesctl get)
idx=0
for i in "${!profiles[@]}"; do
    [[ "${profiles[$i]}" == "$current" ]] && idx=$i
done
next="${profiles[$(( (idx + 1) % ${#profiles[@]} ))]}"
powerprofilesctl set "$next"
