#!/bin/sh -e
. ../common-script.sh
checkEnv
case "$PACKAGER" in
    pacman | apk) pkg_install openssh ;;
    *) pkg_install openssh-server ;;
esac
if command_exists systemctl; then
    "$ESCALATION_TOOL" systemctl enable --now ssh 2>/dev/null || "$ESCALATION_TOOL" systemctl enable --now sshd
    printf "%b\n" "${GREEN}SSH server enabled and started.${RC}"
else
    printf "%b\n" "${YELLOW}No systemd: start the SSH service manually.${RC}"
fi
