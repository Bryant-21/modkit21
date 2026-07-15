#!/usr/bin/env bash
# modkit.sh — bash-friendly wrapper for the modkit CLI.
#
# Resolves its own directory (following symlinks), then dispatches to:
#   1. modkit.exe next to this script, if present
#   2. `uv run python -m cli.main` as a fallback (dev mode, no exe built yet)
#
# Usage: ./modkit.sh data search records "combat shotgun"
#
# Install a personal shim on PATH by symlinking or sourcing this file, e.g.:
#   ln -s "$(pwd)/modkit.sh" ~/.local/bin/modkit

set -e

# Resolve the real directory of this script, following symlinks.
source="${BASH_SOURCE[0]}"
while [ -L "$source" ]; do
    dir="$(cd -P "$(dirname "$source")" && pwd)"
    source="$(readlink "$source")"
    [[ "$source" != /* ]] && source="$dir/$source"
done
SCRIPT_DIR="$(cd -P "$(dirname "$source")" && pwd)"

EXE="$SCRIPT_DIR/modkit.exe"

if [ -x "$EXE" ] || [ -f "$EXE" ]; then
    exec "$EXE" "$@"
fi

# Fallback: run from source via uv. Requires uv and a synced venv.
if command -v uv >/dev/null 2>&1; then
    cd "$SCRIPT_DIR"
    exec uv run python -m cli.main "$@"
fi

echo "modkit.sh: could not find modkit.exe at $EXE and 'uv' is not on PATH" >&2
echo "  Build the exe with: build_modkit_cli.bat" >&2
exit 127
