#!/bin/sh
#
# Render the source tree the way `chezmoi init && chezmoi apply` would on
# HOST, without being on HOST: the hostname is faked with --override-data,
# so this runs on any machine (or a CI runner). In order:
#
#   1. .chezmoi.toml.tmpl -> ci/out/<host>/chezmoi.toml (the host's data)
#   2. every *.tmpl in the tree executed against that data; scripts and
#      init.lua are kept for the other checks, the rest just has to render
#   3. `chezmoi managed` — the target list, which must be $HOME dotfiles
#      only (a stray README.md in $HOME is what this once missed)
#   4. `chezmoi apply --dry-run` into an empty directory: the full apply
#      plan (attributes, ignores, encodings) with nothing written and no
#      script run
#
#   ci/render.sh HOST [VARIANT]        (VARIANT `default` = none)
#
# HOST is a table in .hosts.toml, or `_empty` for a machine registered
# with an empty table — the state a new host starts in, every default in
# play. VARIANT flips settings on top of the host's own (see the case
# below) to reach template branches no real host has enabled.

set -eu
cd "$(dirname "$0")/.."

host=$1
variant=${2:-}
[ "$variant" != default ] || variant=''
out="ci/out/$host${variant:+-$variant}"
rm -rf "$out"
mkdir -p "$out/scripts" "$out/home"

# `_empty` isn't in .hosts.toml — render from a copy of the tree with the
# table appended rather than editing the real file.
src=.
if [ "$host" = _empty ]; then
    src="$out/source"
    mkdir -p "$src"
    git ls-files -z | tar --null -T - -cf - | tar -C "$src" -xf -
    printf '\n[_empty]\n' >> "$src/.hosts.toml"
fi

case $variant in
    '') data='{}' ;;
    # A server: no desktop, and with it nothing that only makes sense
    # under one.
    headless) data='{
        "desktop": {"enabled": false},
        "greeter": {"enabled": false},
        "nvidia": {"enabled": false},
        "fcitx5": {"enabled": false},
        "ide": {"vscode": {"enabled": false}}
    }' ;;
    # The zsh side of the tree, which no registered host has switched on.
    zsh) data='{"shell": {"zsh": {"enabled": true, "oh_my_zsh": {"enabled": true}}}}' ;;
    *) echo "unknown variant: $variant" >&2; exit 2 ;;
esac
override=$(jq -nc --arg host "$host" --argjson data "$data" '{chezmoi: {hostname: $host}} + $data')

echo "==> $host${variant:+ ($variant)}"

chezmoi --source "$src" --override-data "$override" execute-template \
    < "$src/.chezmoi.toml.tmpl" > "$out/chezmoi.toml"

cz() {
    chezmoi --source "$src" --config "$out/chezmoi.toml" --override-data "$override" \
        --destination "$out/home" --persistent-state "$out/state.db" --cache "$out/cache" "$@"
}

fail=0
for f in .chezmoiignore.tmpl $(git ls-files --cached --others --exclude-standard | grep '\.tmpl$' | grep -v '^\.chezmoi\.toml\.tmpl$'); do
    case $f in
        .chezmoiscripts/*) dest="$out/scripts/$(basename "$f" .tmpl)" ;;
        dot_config/nvim/init.lua.tmpl) dest="$out/init.lua" ;;
        *) dest=/dev/null ;;
    esac
    if ! cz execute-template < "$src/$f" > "$dest" 2> "$out/err"; then
        echo "FAIL $f:"
        sed 's/^/    /' "$out/err"
        fail=1
    fi
done

cz managed > "$out/managed"
if stray=$(grep -v '^\.' "$out/managed"); then
    echo "FAIL targets outside \$HOME's dotfiles (add them to .chezmoiignore.tmpl):"
    echo "$stray" | sed 's/^/    /'
    fail=1
fi

if ! cz apply --dry-run > "$out/err" 2>&1; then
    echo "FAIL chezmoi apply --dry-run:"
    sed 's/^/    /' "$out/err"
    fail=1
fi

echo "    $(wc -l < "$out/managed") targets, $(ls "$out/scripts" | wc -l) scripts rendered"
exit $fail
