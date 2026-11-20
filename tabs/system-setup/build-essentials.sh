#!/bin/sh -e
. ../common-script.sh
checkEnv
case "$PACKAGER" in
    apt-get) pkg_install build-essential ;;
    dnf)     "$ESCALATION_TOOL" dnf groupinstall -y "Development Tools" ;;
    pacman)  pkg_install base-devel ;;
    zypper)  "$ESCALATION_TOOL" zypper install -y -t pattern devel_basis ;;
    apk)     pkg_install build-base ;;
    *)       printf "%b\n" "${RED}Unsupported package manager${RC}"; exit 1 ;;
esac
