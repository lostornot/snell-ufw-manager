#!/usr/bin/env bash
set -euo pipefail

USER_NAME="${USER_NAME:-snellmgr}"
LIB_DIR="/usr/local/lib/snell-ufw-control"
ENTRYPOINT="/usr/local/sbin/snell-fwctl"
SNELLCTL="/usr/local/lib/snell-ufw-control/snellctl"
UFWCTL="/usr/local/lib/snell-ufw-control/ufwctl"
SYSTEMCTL="/usr/local/lib/snell-ufw-control/systemctl"
SUDOERS_FILE="/etc/sudoers.d/snell-ufw-control"

command -v python3 >/dev/null

if ! id "$USER_NAME" >/dev/null 2>&1; then
  useradd --system --create-home --shell /bin/bash "$USER_NAME"
fi

install -d -m 0755 "$LIB_DIR"
install -m 0755 node/snell-fwctl "$ENTRYPOINT"
install -m 0755 node/snellctl "$SNELLCTL"
install -m 0755 node/ufwctl "$UFWCTL"
install -m 0755 node/systemctl "$SYSTEMCTL"
chown root:root "$ENTRYPOINT" "$SNELLCTL" "$UFWCTL" "$SYSTEMCTL"
chmod 0755 "$ENTRYPOINT" "$SNELLCTL" "$UFWCTL" "$SYSTEMCTL"

cat > "$SUDOERS_FILE" <<EOF
$USER_NAME ALL=(root) NOPASSWD: /usr/local/sbin/snell-fwctl
EOF
chmod 0440 "$SUDOERS_FILE"
visudo -cf "$SUDOERS_FILE"

cat <<EOF
Node tools installed.

Recommended ~/.ssh/config entry on the controller:

Host my-snell-node
    HostName <node-ip>
    User $USER_NAME
    Port 22
    IdentityFile ~/.ssh/snell_control_ed25519

Use ssh_alias=my-snell-node in snell-ufw-control.
EOF
