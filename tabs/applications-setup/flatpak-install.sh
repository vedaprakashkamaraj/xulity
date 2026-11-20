#!/bin/sh -e
# Generic Flathub installer: flatpak-install.sh <app-id>...
. ../common-script.sh
checkEnv
checkFlatpak
for id in "$@"; do
    printf "%b\n" "${YELLOW}Installing ${id} from Flathub...${RC}"
    flatpak install --user -y flathub "$id"
done
printf "%b\n" "${GREEN}Done. The app may appear in your menu after you log out and back in.${RC}"
