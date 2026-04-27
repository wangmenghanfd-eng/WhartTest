#!/bin/bash
set -euo pipefail

PLIST_PATH="${HOME}/Library/LaunchAgents/com.wharttest.actuator.plist"
LABEL="com.wharttest.actuator"

launchctl bootout "gui/$(id -u)" "${PLIST_PATH}" >/dev/null 2>&1 || true
rm -f "${PLIST_PATH}"

echo "已卸载 LaunchAgent: ${LABEL}"
