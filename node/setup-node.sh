#!/bin/bash
# setup-node.sh — One-time setup for Snell UFW Manager on a node VPS
# Creates snellmgr user, deploys snell-fwctl, configures sudo & SSH
#
# Usage:
#   bash setup-node.sh --key 'ssh-ed25519 AAAA...' [--from '控制中心IP']
#
# Must be run as root.

set -euo pipefail

# ─── Colors & Formatting ────────────────────────────────────────────────────

readonly RED='\033[0;31m'
readonly GREEN='\033[0;32m'
readonly YELLOW='\033[1;33m'
readonly CYAN='\033[0;36m'
readonly BOLD='\033[1m'
readonly NC='\033[0m'  # No Color

step_ok() {
    echo -e "  ${GREEN}✓${NC} $1"
}

step_fail() {
    echo -e "  ${RED}✗${NC} $1"
}

step_info() {
    echo -e "  ${CYAN}→${NC} $1"
}

section() {
    echo ""
    echo -e "${BOLD}${YELLOW}[$1]${NC}"
}

# ─── Usage ───────────────────────────────────────────────────────────────────

usage() {
    cat <<EOF
${BOLD}Snell UFW Manager — Node Setup${NC}

Usage:
  bash setup-node.sh --key '<ssh_public_key>' [--from '<controller_ip>']

Arguments:
  --key  <pubkey>   (REQUIRED) SSH public key for the snellmgr user
  --from <ip>       (OPTIONAL) Restrict SSH access to this source IP
  --help            Show this help message

Example:
  bash setup-node.sh --key 'ssh-ed25519 AAAA... admin@controller' --from '203.0.113.10'
EOF
    exit 0
}

# ─── Parse Arguments ─────────────────────────────────────────────────────────

SSH_KEY=""
FROM_IP=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --key)
            SSH_KEY="${2:-}"
            if [[ -z "$SSH_KEY" ]]; then
                echo -e "${RED}Error: --key requires a public key string${NC}"
                exit 1
            fi
            shift 2
            ;;
        --from)
            FROM_IP="${2:-}"
            if [[ -z "$FROM_IP" ]]; then
                echo -e "${RED}Error: --from requires an IP address${NC}"
                exit 1
            fi
            shift 2
            ;;
        --help|-h)
            usage
            ;;
        *)
            echo -e "${RED}Error: unknown argument: $1${NC}"
            usage
            ;;
    esac
done

if [[ -z "$SSH_KEY" ]]; then
    echo -e "${RED}Error: --key is required${NC}"
    echo ""
    usage
fi

# ─── Pre-flight checks ──────────────────────────────────────────────────────

if [[ "$(id -u)" -ne 0 ]]; then
    echo -e "${RED}Error: This script must be run as root${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FWCTL_SRC="${SCRIPT_DIR}/snell-fwctl"

if [[ ! -f "$FWCTL_SRC" ]]; then
    echo -e "${RED}Error: snell-fwctl not found in ${SCRIPT_DIR}${NC}"
    echo "Both scripts should be in the same directory."
    exit 1
fi

readonly SNELLMGR_USER="snellmgr"
readonly FWCTL_DEST="/usr/local/sbin/snell-fwctl"
readonly SUDOERS_FILE="/etc/sudoers.d/snellmgr"
readonly BACKUP_DIR="/opt/snell-fwctl/backups"

ERRORS=0

echo ""
echo -e "${BOLD}╔══════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║   Snell UFW Manager — Node Setup             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  Hostname:   ${CYAN}$(hostname)${NC}"
echo -e "  Date:       ${CYAN}$(date '+%Y-%m-%d %H:%M:%S %Z')${NC}"
echo -e "  SSH Key:    ${CYAN}${SSH_KEY:0:40}...${NC}"
if [[ -n "$FROM_IP" ]]; then
echo -e "  From IP:    ${CYAN}${FROM_IP}${NC}"
fi

# ─── Step 1: Create snellmgr user ───────────────────────────────────────────

section "1/7  Create snellmgr user"

if id "$SNELLMGR_USER" &>/dev/null; then
    step_info "User '${SNELLMGR_USER}' already exists"
    step_ok "User exists"
else
    if useradd --system --shell /bin/bash --create-home "$SNELLMGR_USER" 2>/dev/null; then
        step_ok "Created system user '${SNELLMGR_USER}'"
    else
        step_fail "Failed to create user '${SNELLMGR_USER}'"
        (( ERRORS++ ))
    fi
fi

# ─── Step 2: Deploy snell-fwctl ──────────────────────────────────────────────

section "2/7  Deploy snell-fwctl"

if cp "$FWCTL_SRC" "$FWCTL_DEST" 2>/dev/null; then
    step_ok "Copied to ${FWCTL_DEST}"
else
    step_fail "Failed to copy snell-fwctl to ${FWCTL_DEST}"
    (( ERRORS++ ))
fi

if chown root:root "$FWCTL_DEST" 2>/dev/null && chmod 755 "$FWCTL_DEST" 2>/dev/null; then
    step_ok "Set ownership root:root, mode 755"
else
    step_fail "Failed to set permissions on ${FWCTL_DEST}"
    (( ERRORS++ ))
fi

# ─── Step 3: Configure sudoers ──────────────────────────────────────────────

section "3/7  Configure sudoers"

SUDOERS_CONTENT="${SNELLMGR_USER} ALL=(root) NOPASSWD: ${FWCTL_DEST} *"

echo "$SUDOERS_CONTENT" > "$SUDOERS_FILE"
chmod 440 "$SUDOERS_FILE"

# Validate sudoers file
if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
    step_ok "Sudoers configured: ${SUDOERS_FILE}"
    step_info "${SNELLMGR_USER} can run: sudo ${FWCTL_DEST} <any args>"
else
    step_fail "Sudoers syntax error — removing ${SUDOERS_FILE}"
    rm -f "$SUDOERS_FILE"
    (( ERRORS++ ))
fi

# ─── Step 4: Deploy SSH authorized_keys ──────────────────────────────────────

section "4/7  Deploy SSH authorized_keys"

SSH_DIR="$(eval echo ~${SNELLMGR_USER})/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

mkdir -p "$SSH_DIR"
chmod 700 "$SSH_DIR"
chown "${SNELLMGR_USER}:${SNELLMGR_USER}" "$SSH_DIR" 2>/dev/null || \
    chown "${SNELLMGR_USER}:" "$SSH_DIR"

# Build key line with optional from= restriction
KEY_LINE="$SSH_KEY"
if [[ -n "$FROM_IP" ]]; then
    KEY_LINE="from=\"${FROM_IP}\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding ${SSH_KEY}"
    step_info "SSH restricted to from=${FROM_IP}"
else
    KEY_LINE="no-port-forwarding,no-X11-forwarding,no-agent-forwarding ${SSH_KEY}"
    step_info "SSH key deployed (no IP restriction)"
fi

# Write the key (overwrite to ensure clean state)
echo "$KEY_LINE" > "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"
chown "${SNELLMGR_USER}:${SNELLMGR_USER}" "$AUTH_KEYS" 2>/dev/null || \
    chown "${SNELLMGR_USER}:" "$AUTH_KEYS"

step_ok "Authorized keys deployed to ${AUTH_KEYS}"

# ─── Step 5: Create backup directory ────────────────────────────────────────

section "5/7  Create backup directory"

if mkdir -p "$BACKUP_DIR" 2>/dev/null; then
    chown "${SNELLMGR_USER}:${SNELLMGR_USER}" "$BACKUP_DIR" 2>/dev/null || \
        chown "${SNELLMGR_USER}:" "$BACKUP_DIR" 2>/dev/null || true
    # Root needs to own parent for security, but backup dir is for convenience
    chown root:root /opt/snell-fwctl 2>/dev/null || true
    chmod 755 /opt/snell-fwctl 2>/dev/null || true
    chmod 755 "$BACKUP_DIR" 2>/dev/null || true
    step_ok "Backup directory: ${BACKUP_DIR}"
else
    step_fail "Failed to create ${BACKUP_DIR}"
    (( ERRORS++ ))
fi

# ─── Step 6: Ensure UFW is installed, configured, and active ─────────────────

section "6/7  Ensure UFW installation and status"

# 1. Install UFW if missing
if ! command -v ufw &>/dev/null; then
    step_info "UFW is not installed. Installing ufw..."
    if apt-get update -qq && apt-get install -y ufw; then
        step_ok "UFW installed successfully"
    else
        step_fail "Failed to install UFW"
        (( ERRORS++ ))
    fi
fi

if command -v ufw &>/dev/null; then
    # 2. Prevent SSH lockout: Detect SSH ports and allow them
    ssh_ports=("22")
    
    # Detect from sshd config
    if [[ -f /etc/ssh/sshd_config ]]; then
        config_port=$(grep -i '^Port ' /etc/ssh/sshd_config | awk '{print $2}' || true)
        if [[ -n "$config_port" ]]; then
            ssh_ports+=("$config_port")
        fi
    fi
    if [[ -d /etc/ssh/sshd_config.d ]]; then
        d_port=$(grep -rh -i '^Port ' /etc/ssh/sshd_config.d/ 2>/dev/null | awk '{print $2}' || true)
        if [[ -n "$d_port" ]]; then
            ssh_ports+=("$d_port")
        fi
    fi
    # Detect from current SSH connection env
    if [[ -n "${SSH_CONNECTION:-}" ]]; then
        conn_port=$(echo "$SSH_CONNECTION" | awk '{print $4}')
        if [[ -n "$conn_port" ]]; then
            ssh_ports+=("$conn_port")
        fi
    fi

    # Allow detected SSH ports
    step_info "Ensuring SSH is allowed in UFW..."
    ufw allow ssh &>/dev/null || true
    for p in "${ssh_ports[@]}"; do
        if [[ -n "$p" && "$p" =~ ^[0-9]+$ ]]; then
            ufw allow "$p"/tcp &>/dev/null || true
        fi
    done

    # 3. Enable UFW if inactive
    if ufw status | grep -q "Status: active"; then
        step_ok "UFW is already active"
    else
        step_info "Activating UFW..."
        if ufw --force enable &>/dev/null; then
            step_ok "UFW enabled and active"
        else
            step_fail "Failed to enable UFW"
            (( ERRORS++ ))
        fi
    fi

    # 4. Enable UFW logging
    if ufw logging on &>/dev/null; then
        step_ok "UFW logging enabled"
    else
        step_fail "Failed to enable UFW logging"
        (( ERRORS++ ))
    fi
else
    step_fail "UFW command still missing"
    (( ERRORS++ ))
fi


# ─── Step 7: Test snell-fwctl ────────────────────────────────────────────────

section "7/7  Test snell-fwctl"

step_info "Running: sudo -u ${SNELLMGR_USER} sudo ${FWCTL_DEST} status"

TEST_OUTPUT=$(sudo -u "$SNELLMGR_USER" sudo "$FWCTL_DEST" status 2>&1) || true

if echo "$TEST_OUTPUT" | grep -q '"ok": true'; then
    step_ok "snell-fwctl status test passed"
    step_info "Output: ${TEST_OUTPUT}"
else
    step_fail "snell-fwctl status test failed"
    step_info "Output: ${TEST_OUTPUT}"
    (( ERRORS++ ))
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

echo ""
echo -e "${BOLD}════════════════════════════════════════════════${NC}"

if (( ERRORS == 0 )); then
    echo -e "${GREEN}${BOLD}  ✓ Setup completed successfully!${NC}"
    echo ""
    echo -e "  The controller can now connect with:"
    echo -e "  ${CYAN}ssh ${SNELLMGR_USER}@$(hostname -I 2>/dev/null | awk '{print $1}' || echo '<this-ip>') sudo snell-fwctl status${NC}"
else
    echo -e "${RED}${BOLD}  ✗ Setup completed with ${ERRORS} error(s)${NC}"
    echo ""
    echo -e "  Please review the errors above and fix them manually."
fi

echo ""
exit "$ERRORS"
