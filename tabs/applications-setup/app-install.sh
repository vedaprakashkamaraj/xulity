#!/bin/sh -e
# Generic installer: app-install.sh <generic-name>...
. ../common-script.sh
checkEnv

mapName() {
    case "$1:$PACKAGER" in
        python3:pacman) echo python ;;
        jdk:apt-get) echo default-jdk ;;
        jdk:dnf | jdk:zypper) echo java-21-openjdk-devel ;;
        jdk:pacman) echo jdk-openjdk ;;
        jdk:apk) echo openjdk21 ;;
        jdk:brew) echo openjdk ;;
        libreoffice:pacman) echo libreoffice-fresh ;;
        gh:pacman | gh:apk) echo github-cli ;;
        fd:apt-get | fd:dnf) echo fd-find ;;
        delta:pacman | delta:dnf | delta:zypper | delta:brew | delta:apk) echo git-delta ;;
        7zip:apt-get) echo p7zip-full ;;
        7zip:dnf | 7zip:zypper | 7zip:apk) echo p7zip ;;
        7zip:pacman) echo 7zip ;;
        7zip:brew) echo sevenzip ;;
        *) echo "$1" ;;
    esac
}

if [ "$PACKAGER" = "apt-get" ]; then
    "$ESCALATION_TOOL" apt-get update
fi

pkgs=""
for a in "$@"; do pkgs="$pkgs $(mapName "$a")"; done
printf "%b\n" "${YELLOW}Installing:${pkgs}${RC}"
# shellcheck disable=SC2086
pkg_install $pkgs
printf "%b\n" "${GREEN}Done.${RC}"
