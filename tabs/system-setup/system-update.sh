#!/bin/sh -e
. ../common-script.sh
checkEnv
case "$PACKAGER" in
    apt-get) "$ESCALATION_TOOL" apt-get update; "$ESCALATION_TOOL" apt-get upgrade -y ;;
    dnf)     "$ESCALATION_TOOL" dnf upgrade -y ;;
    pacman)  "$ESCALATION_TOOL" pacman -Syu --noconfirm ;;
    zypper)  "$ESCALATION_TOOL" zypper refresh; "$ESCALATION_TOOL" zypper update -y ;;
    apk)     "$ESCALATION_TOOL" apk update; "$ESCALATION_TOOL" apk upgrade ;;
    brew)    brew update; brew upgrade ;;
esac
printf "%b\n" "${GREEN}System updated.${RC}"
