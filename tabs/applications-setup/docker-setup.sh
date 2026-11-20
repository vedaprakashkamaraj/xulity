#!/bin/sh -e
. ../common-script.sh
checkEnv
if command_exists docker; then
    printf "%b\n" "${CYAN}Docker is already installed${RC}"; exit 0
fi
printf "%b" "${YELLOW}This downloads and runs Docker's official script (get.docker.com) as root. Continue? [y/N] ${RC}"
read -r answer
[ "$answer" = "y" ] || { printf "%b\n" "${RED}Cancelled${RC}"; exit 1; }
tmp=$(mktemp)
trap 'rm -f "$tmp"' 0
curl -fsSL https://get.docker.com -o "$tmp"
"$ESCALATION_TOOL" sh "$tmp"
if [ -n "$USER" ] && [ "$(id -u)" != "0" ]; then
    "$ESCALATION_TOOL" usermod -aG docker "$USER"
    printf "%b\n" "${YELLOW}Log out and back in for the docker group to apply.${RC}"
fi
