#!/bin/sh -e
# Homebrew installer (macOS): brew-install.sh <formula:name | cask:name>...
# "name|fallback" tries the alternatives in order (Homebrew renames casks now and then).
. ../common-script.sh
if ! command_exists brew; then
    printf "%b\n" "${RED}Homebrew is not installed. Install it from https://brew.sh, open a new terminal, then run this again.${RC}"
    exit 1
fi
for spec in "$@"; do
    kind=${spec%%:*}
    names=${spec#*:}
    flag="--formula"
    [ "$kind" = "cask" ] && flag="--cask"
    ok=0
    for name in $(printf '%s' "$names" | tr '|' ' '); do
        printf "%b\n" "${YELLOW}Installing ${name} (${kind}) with Homebrew...${RC}"
        if brew install $flag "$name"; then ok=1; break; fi
    done
    if [ "$ok" != 1 ]; then
        printf "%b\n" "${RED}Could not install ${names}${RC}"; exit 1
    fi
    case "$names" in
        openjdk*) printf "%b\n" "${CYAN}Make it visible to the system JDK tools with:${RC}\n  sudo ln -sfn \$(brew --prefix)/opt/${names%%|*}/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/${names%%|*}.jdk" ;;
    esac
done
printf "%b\n" "${GREEN}Done.${RC}"
