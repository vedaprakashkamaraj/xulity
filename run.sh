#!/bin/sh
# Launcher for Linux/macOS: finds Python 3.11+ and starts xutil.
dir=$(cd "$(dirname "$0")" && pwd)
for py in python3.13 python3.12 python3.11 python3; do
    if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        exec "$py" "$dir/xutil.py" "$@"
    fi
done
echo "xutil needs Python 3.11+. Install it with your package manager." >&2; exit 1
