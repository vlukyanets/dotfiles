#!/bin/sh
#
# The parts a render doesn't prove: data files parse on their own, and
# docs/host-config/README.md's numbered script list still matches the
# scripts in .chezmoiscripts (the numbers are the link between the two —
# when a script is added or renumbered, the list has to follow).

set -eu
cd "$(dirname "$0")/.."

fail=0

echo "==> .hosts.toml"
python3 -c 'import tomllib; tomllib.load(open(".hosts.toml", "rb"))' || fail=1

echo "==> JSON"
for f in $(git ls-files '*.json'); do
    jq empty "$f" || { echo "FAIL $f"; fail=1; }
done

echo "==> script numbering vs docs/host-config/README.md"
scripts=$(ls .chezmoiscripts | sed -n 's/^run_once_before_\([0-9][0-9]\)-.*/\1/p')
expected=$(seq -f '%02g' 1 "$(echo "$scripts" | wc -l)")
if [ "$scripts" != "$expected" ]; then
    echo "FAIL scripts aren't numbered 01..N without gaps or duplicates:"
    ls .chezmoiscripts | sed 's/^/    /'
    fail=1
fi
listed=$(sed -n '/^## Scripts/,/^\[/p' docs/host-config/README.md | grep -c '^[0-9][0-9]*\. \[' || true)
if [ "$listed" != "$(echo "$scripts" | wc -l)" ]; then
    echo "FAIL docs/host-config/README.md lists $listed scripts, .chezmoiscripts has $(echo "$scripts" | wc -l)"
    fail=1
fi

exit $fail
