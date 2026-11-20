#!/bin/sh
# One-line launcher for Linux/macOS:
#   curl -fsSL https://raw.githubusercontent.com/YOUR_USER/xutil/main/get.sh | sh
# Downloads xutil into a temp folder, runs it, then cleans up.
REPO="${XUTIL_REPO:-YOUR_USER/xutil}"
BRANCH="${XUTIL_BRANCH:-main}"

for cmd in curl tar; do
    command -v "$cmd" >/dev/null 2>&1 || { echo "Need $cmd installed." >&2; exit 1; }
done
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT INT TERM
curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$tmp" --strip-components=1 || exit 1
# stdin is the pipe here, so give xutil the real terminal
sh "$tmp/run.sh" "$@" </dev/tty
