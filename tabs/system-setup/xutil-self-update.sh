#!/bin/sh -e
# Refresh the installed xutil from the downloaded source folder.
# Override the source location with XUTIL_SOURCE_DIR=/path/to/xutil.
SRC="${XUTIL_SOURCE_DIR:-$HOME/Downloads/xutil}"

if [ ! -f "$SRC/install.sh" ]; then
    printf "Cannot find xutil source at %s\nSet XUTIL_SOURCE_DIR to the folder that contains install.sh.\n" "$SRC" >&2
    exit 1
fi

printf "Updating xutil from %s\n" "$SRC"
exec sh "$SRC/install.sh" --no-deps "$@"
