#!/bin/sh -e
# Shared helpers for Linux/macOS scripts (counterpart of common-script.ps1).
# shellcheck disable=SC2034

RC='\033[0m'; RED='\033[31m'; YELLOW='\033[33m'; CYAN='\033[36m'; GREEN='\033[32m'

command_exists() {
    for cmd in "$@"; do command -v "$cmd" >/dev/null 2>&1 || return 1; done
    return 0
}

checkEscalationTool() {
    # GUI mode: xutil points this at a wrapper that shows a password dialog
    if [ -n "$XUTIL_ESCALATION" ]; then ESCALATION_TOOL=$XUTIL_ESCALATION; return 0; fi
    if [ "$(id -u)" = "0" ]; then ESCALATION_TOOL="env"; return 0; fi
    for tool in sudo doas; do
        if command_exists "$tool"; then ESCALATION_TOOL=$tool; return 0; fi
    done
    printf "%b\n" "${RED}No supported privilege-escalation tool (sudo/doas) found${RC}"; exit 1
}

checkPackageManager() {
    for pgm in apt-get dnf pacman zypper apk brew; do
        if command_exists "$pgm"; then PACKAGER=$pgm; break; fi
    done
    if [ -z "$PACKAGER" ]; then
        printf "%b\n" "${RED}No supported package manager found${RC}"; exit 1
    fi
    printf "%b\n" "${CYAN}Using ${PACKAGER} as package manager${RC}"
}

checkDistro() {
    DTYPE="unknown"
    if [ -f /etc/os-release ]; then . /etc/os-release; DTYPE=$ID; fi
}

checkEnv() {
    checkEscalationTool
    checkPackageManager
    checkDistro
}

# pkg_install <package...>  (installs with the detected package manager)
pkg_install() {
    case "$PACKAGER" in
        apt-get) "$ESCALATION_TOOL" apt-get install -y "$@" ;;
        dnf)     "$ESCALATION_TOOL" dnf install -y "$@" ;;
        pacman)  "$ESCALATION_TOOL" pacman -S --needed --noconfirm "$@" ;;
        zypper)  "$ESCALATION_TOOL" zypper install -y "$@" ;;
        apk)     "$ESCALATION_TOOL" apk add "$@" ;;
        brew)    brew install "$@" ;;
    esac
}

# checkFlatpak: make sure flatpak and the Flathub remote exist (user scope, no root for apps)
checkFlatpak() {
    if ! command_exists flatpak; then
        printf "%b\n" "${YELLOW}Installing Flatpak...${RC}"
        pkg_install flatpak
    fi
    flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
}
