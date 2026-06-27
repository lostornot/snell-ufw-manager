#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${USER_NAME:-snellmgr}"
REMOVE_USER="${REMOVE_USER:-0}"
LIB_DIR="/usr/local/lib/snell-ufw-control"
ENTRYPOINT="/usr/local/sbin/snell-fwctl"
SUDOERS_FILE="/etc/sudoers.d/snell-ufw-control"

rm -f "$ENTRYPOINT"
rm -f "$LIB_DIR/snellctl"
rm -f "$LIB_DIR/ufwctl"
rm -f "$LIB_DIR/systemctl"
rmdir "$LIB_DIR" 2>/dev/null || true
rm -f "$SUDOERS_FILE"

if [[ "$REMOVE_USER" == "1" ]] && id "$USER_NAME" >/dev/null 2>&1; then
  userdel -r "$USER_NAME"
fi

cat <<EOF
Node tools removed.

Removed:
  $ENTRYPOINT
  $LIB_DIR/snellctl
  $LIB_DIR/ufwctl
  $LIB_DIR/systemctl
  $SUDOERS_FILE

Not touched:
  Snell service and configuration
  UFW rules
  SSH authorized_keys outside $USER_NAME home
EOF
