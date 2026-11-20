#!/bin/sh -e
# .NET SDK (LTS) via Microsoft's official dotnet-install script, installed per user into ~/.dotnet (no root).
. ../common-script.sh
if command_exists dotnet; then
    printf "%b\n" "${CYAN}.NET is already installed:${RC} $(dotnet --version 2>/dev/null)"; exit 0
fi
command_exists curl || { printf "%b\n" "${RED}curl is needed. Install it from the Utilities list first.${RC}"; exit 1; }
command_exists bash || { printf "%b\n" "${RED}bash is needed by Microsoft's installer.${RC}"; exit 1; }
printf "%b" "${YELLOW}This downloads and runs Microsoft's official script (https://dot.net/v1/dotnet-install.sh) and installs the .NET SDK (LTS) into ~/.dotnet. Continue? [y/N] ${RC}"
read -r answer
[ "$answer" = "y" ] || { printf "%b\n" "${RED}Cancelled${RC}"; exit 1; }
tmp=$(mktemp)
trap 'rm -f "$tmp"' 0
curl -fsSL https://dot.net/v1/dotnet-install.sh -o "$tmp"
bash "$tmp" --channel LTS --install-dir "$HOME/.dotnet"
line='export DOTNET_ROOT="$HOME/.dotnet"; export PATH="$PATH:$HOME/.dotnet:$HOME/.dotnet/tools"'
if ! grep -qs 'DOTNET_ROOT' "$HOME/.profile" 2>/dev/null; then
    printf "%b" "${YELLOW}Add dotnet to your PATH in ~/.profile? [y/N] ${RC}"
    read -r answer
    if [ "$answer" = "y" ]; then
        printf "\n# .NET SDK (added by xutil)\n%s\n" "$line" >> "$HOME/.profile"
        printf "%b\n" "${GREEN}Added. Log out and back in (or run: . ~/.profile).${RC}"
    else
        printf "%b\n" "${CYAN}Run this in each terminal to use it:${RC}\n  $line"
    fi
fi
printf "%b\n" "${GREEN}Done. If dotnet will not start, install libicu and openssl with your package manager.${RC}"
