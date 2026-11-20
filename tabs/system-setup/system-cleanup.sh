#!/bin/sh -e
. ../common-script.sh
checkEnv
printf "%b" "${YELLOW}Clean package caches, unused packages and old journal logs? [y/N] ${RC}"
read -r answer
[ "$answer" = "y" ] || { printf "%b\n" "${RED}Cancelled${RC}"; exit 1; }
case "$PACKAGER" in
    apt-get) "$ESCALATION_TOOL" apt-get clean; "$ESCALATION_TOOL" apt-get autoremove -y ;;
    dnf)     "$ESCALATION_TOOL" dnf clean all; "$ESCALATION_TOOL" dnf autoremove -y ;;
    pacman)  "$ESCALATION_TOOL" pacman -Sc --noconfirm ;;
    zypper)  "$ESCALATION_TOOL" zypper clean --all ;;
    apk)     "$ESCALATION_TOOL" apk cache clean ;;
    brew)    brew cleanup ;;
esac
if command_exists journalctl; then
    "$ESCALATION_TOOL" journalctl --vacuum-time=7d
fi
printf "%b\n" "${GREEN}Cleanup finished.${RC}"
