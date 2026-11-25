#!/bin/sh -e
# Install common printer drivers and printing services (CUPS) on Linux.
# Asks before making changes. Supports major distros via the detected package manager.
. ../common-script.sh
checkEnv

printf "%b\n" "${CYAN}This installs printing support (CUPS) and common printer drivers.${RC}"
printf "%b\n" "${YELLOW}Packages may include: CUPS, HP (hplip), Gutenprint, Foomatic, printer drivers.${RC}"
printf "Continue? [y/N] "; read -r ans
case "$ans" in [Yy]*) ;; *) printf "Cancelled.\n"; exit 0 ;; esac

if [ "$PACKAGER" = "apt-get" ]; then
    "$ESCALATION_TOOL" apt-get update
fi

case "$PACKAGER" in
    apt-get)
        pkgs="cups cups-client cups-filters system-config-printer printer-driver-all hplip printer-driver-gutenprint printer-driver-foomatic-db foomatic-db-compressed-ppds openprinting-ppds"
        ;;
    dnf)
        pkgs="cups cups-filters system-config-printer gutenprint-cups hplip foomatic foomatic-db foomatic-db-ppds"
        ;;
    pacman)
        pkgs="cups cups-filters system-config-printer gutenprint hplip foomatic-db-engine foomatic-db foomatic-db-ppds foomatic-db-nonfree-ppds"
        ;;
    zypper)
        pkgs="cups cups-filters system-config-printer gutenprint hplip foomatic-filters foomatic-db"
        ;;
    apk)
        pkgs="cups cups-filters cups-client hplip gutenprint"
        ;;
    brew)
        printf "%b\n" "${YELLOW}macOS printing drivers are usually provided by the OS/vendor. Skipping Linux printer packages.${RC}"
        exit 0
        ;;
    *)
        printf "%b\n" "${RED}Unsupported package manager: $PACKAGER${RC}"
        exit 1
        ;;
esac

printf "%b\n" "${YELLOW}Installing:${RC} $pkgs"
# shellcheck disable=SC2086
pkg_install $pkgs

# Enable CUPS where systemd is present
if command_exists systemctl; then
    "$ESCALATION_TOOL" systemctl enable --now cups.service 2>/dev/null || "$ESCALATION_TOOL" systemctl enable --now cups 2>/dev/null || true
    "$ESCALATION_TOOL" systemctl enable --now cups-browsed.service 2>/dev/null || true
fi

printf "%b\n" "${GREEN}Printer drivers/services installed. Add printers from your system printer settings or CUPS web UI (http://localhost:631).${RC}"
