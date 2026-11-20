#!/bin/sh -e
. ../common-script.sh
checkEnv
if ! command_exists lynis; then pkg_install lynis; fi
"$ESCALATION_TOOL" lynis audit system
