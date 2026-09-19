#!/bin/sh
#
# Lint what ci/render.sh produced: every rendered run_once_ script through
# `sh -n` and shellcheck (they're POSIX sh, and shellcheck reads the
# shebang), init.lua through luacheck. Linters that aren't installed are
# skipped with a note, so this degrades to a syntax check locally; the
# workflow installs both.

set -eu
cd "$(dirname "$0")/.."

fail=0
have() { command -v "$1" >/dev/null 2>&1; }

scripts=$(find ci/out -path '*/scripts/*.sh' | sort)
[ -n "$scripts" ] || { echo "nothing rendered — run ci/render.sh first" >&2; exit 2; }

echo "==> sh -n"
for s in $scripts; do
    sh -n "$s" || { echo "FAIL $s"; fail=1; }
done

if have shellcheck; then
    echo "==> shellcheck"
    # What one rendering of a template looks like to a linter: code after
    # a templated `exit 0` is unreachable (SC2317, SC2329), a templated
    # boolean makes a constant test (SC2050), a variable another branch
    # sets looks unassigned (SC2154); sourced files aren't here (SC1091).
    shellcheck --exclude=SC2317,SC2329,SC2050,SC2154,SC1091 $scripts || fail=1
else
    echo "==> shellcheck not installed, skipped"
fi

if have luacheck; then
    echo "==> luacheck"
    for f in ci/out/*/init.lua; do
        luacheck --no-color --globals vim -- "$f" || fail=1
    done
else
    echo "==> luacheck not installed, skipped"
fi

exit $fail
