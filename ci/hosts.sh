#!/bin/sh
#
# Every machine registered in .hosts.toml — its top-level tables, one per
# line. The workflow turns this into the render matrix, so a new host gets
# checked from the commit that adds it.

set -eu
cd "$(dirname "$0")/.."

python3 -c 'import tomllib; print("\n".join(tomllib.load(open(".hosts.toml", "rb"))))'
