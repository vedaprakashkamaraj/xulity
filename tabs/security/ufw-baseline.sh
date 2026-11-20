#!/bin/sh -e
. ../common-script.sh
checkEnv
if ! command_exists ufw; then pkg_install ufw; fi
printf "%b" "${YELLOW}Keep SSH (22/tcp) reachable? [Y/n] ${RC}"
read -r answer
if [ "$answer" != "n" ]; then "$ESCALATION_TOOL" ufw allow 22/tcp; fi
"$ESCALATION_TOOL" ufw default deny incoming
"$ESCALATION_TOOL" ufw default allow outgoing
"$ESCALATION_TOOL" ufw --force enable
"$ESCALATION_TOOL" ufw status verbose
