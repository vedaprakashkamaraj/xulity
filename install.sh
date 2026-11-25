#!/bin/sh
# xutil installer for Linux and macOS.
#   ./install.sh              install to ~/.local (no root needed except for missing system packages)
#   ./install.sh --run        install, then open the window
#   ./install.sh --uninstall  remove everything this script added
#   Options: --prefix DIR (default ~/.local)   --no-deps (don't try to install Python/tkinter)
set -e
here=$(cd "$(dirname "$0")" && pwd)
PREFIX="${PREFIX:-$HOME/.local}"; RUN=0; UNINSTALL=0; DEPS=1
while [ $# -gt 0 ]; do
    case "$1" in
        --run) RUN=1 ;;
        --uninstall) UNINSTALL=1 ;;
        --no-deps) DEPS=0 ;;
        --prefix) shift; PREFIX="$1" ;;
        -h|--help) sed -n '2,7p' "$0"; exit 0 ;;
        *) echo "unknown option: $1" >&2; exit 2 ;;
    esac
    shift
done
APPDIR="$PREFIX/share/xutil"; BIN="$PREFIX/bin/xutil"
DESKTOP="$PREFIX/share/applications/xutil.desktop"; ICON="$PREFIX/share/icons/hicolor/256x256/apps/xutil.png"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

if [ "$UNINSTALL" = 1 ]; then
    rm -rf "$APPDIR" "$BIN" "$DESKTOP" "$ICON"
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
    say "xutil removed from $PREFIX"; exit 0
fi

# ---- package manager helpers -------------------------------------------------------
SUDO=""; [ "$(id -u)" = 0 ] || { command -v sudo >/dev/null 2>&1 && SUDO=sudo || { command -v doas >/dev/null 2>&1 && SUDO=doas; }; }
pm_install() {  # pm_install <apt> <dnf> <pacman> <zypper> <apk> <brew>
    if   command -v apt-get >/dev/null 2>&1; then $SUDO apt-get update -qq && $SUDO apt-get install -y $1
    elif command -v dnf     >/dev/null 2>&1; then $SUDO dnf install -y $2
    elif command -v pacman  >/dev/null 2>&1; then $SUDO pacman -S --needed --noconfirm $3
    elif command -v zypper  >/dev/null 2>&1; then $SUDO zypper install -y $4
    elif command -v apk     >/dev/null 2>&1; then $SUDO apk add $5
    elif command -v brew    >/dev/null 2>&1; then brew install $6
    else return 1; fi
}
find_python() {
    for py in python3.13 python3.12 python3.11 python3; do
        if command -v "$py" >/dev/null 2>&1 && "$py" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
            command -v "$py"; return 0
        fi
    done
    return 1
}

# ---- python 3.11+ ------------------------------------------------------------------
PY=$(find_python) || {
    [ "$DEPS" = 1 ] || die "Python 3.11+ is required."
    say "Installing Python 3..."
    pm_install "python3" "python3" "python" "python3" "python3" "python@3.12" || die "Install Python 3.11+ manually, then re-run."
    PY=$(find_python) || die "Python 3.11+ is still missing (your distro ships an older one)."
}
say "Python: $PY ($($PY -V 2>&1))"

# ---- tkinter (the window) ----------------------------------------------------------
if ! "$PY" -c 'import tkinter' 2>/dev/null; then
    [ "$DEPS" = 1 ] || die "tkinter is missing (apt: python3-tk, dnf: python3-tkinter, pacman: tk)."
    say "Installing tkinter..."
    pm_install "python3-tk" "python3-tkinter" "tk" "python3-tk" "py3-tkinter tk" "python-tk@3.12" || die "Install tkinter manually."
    "$PY" -c 'import tkinter' 2>/dev/null || die "tkinter still not importable with $PY."
fi

# ---- copy files --------------------------------------------------------------------
say "Installing to $APPDIR"
rm -rf "$APPDIR"; mkdir -p "$APPDIR" "$PREFIX/bin"
cp -R "$here/xutil.py" "$here/xutil_icons.py" "$here/tabs" "$here/assets" "$APPDIR/"
find "$APPDIR" -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$APPDIR/tabs" -name '*.sh' -exec chmod +x {} +

cat > "$BIN" <<LAUNCH
#!/bin/sh
# xutil launcher: window when a display exists (or with --gui), terminal menu otherwise.
if [ \$# -eq 0 ] && { [ -n "\$DISPLAY" ] || [ -n "\$WAYLAND_DISPLAY" ] || [ "\$(uname)" = Darwin ]; }; then set -- --gui; fi
exec "$PY" "$APPDIR/xutil.py" "\$@"
LAUNCH
chmod +x "$BIN"

# ---- desktop entry (Linux) ---------------------------------------------------------
if [ "$(uname)" != Darwin ]; then
    mkdir -p "$(dirname "$DESKTOP")" "$(dirname "$ICON")"
    cp "$here/assets/xutil.png" "$ICON"
    cat > "$DESKTOP" <<ENTRY
[Desktop Entry]
Type=Application
Name=xutil
Comment=Install apps and set up your system
Exec=$BIN --gui
Icon=$ICON
Terminal=false
Categories=System;Settings;Utility;
Keywords=install;setup;apps;
StartupWMClass=xutil
ENTRY
    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$PREFIX/share/applications" 2>/dev/null || true
fi

"$PY" "$APPDIR/xutil.py" --check
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) say "Add $PREFIX/bin to your PATH to type 'xutil' in a terminal." ;; esac
say "Installed. Start it from your app menu, or run: xutil"
if [ "$RUN" = 1 ]; then say "Launching xutil..."; exec "$BIN" "$@"; fi
