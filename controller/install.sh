#!/bin/bash
# Snell UFW Manager — Controller Install Script
# Run on the control center VPS as root.

set -euo pipefail

APP_DIR="/opt/snell-ufw-manager"
VENV_DIR="${APP_DIR}/venv"
DATA_DIR="${APP_DIR}/controller/data"
BACKUP_DIR="${APP_DIR}/backups"
SSH_KEY="/root/.ssh/snellmgr_ed25519"
SERVICE_NAME="snell-ufw-manager"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "  ${GREEN}✓${NC} $1"; }
warn()  { echo -e "  ${YELLOW}⚠${NC} $1"; }
error() { echo -e "  ${RED}✗${NC} $1"; }

echo ""
echo "══════════════════════════════════════════"
echo " Snell UFW Manager — 控制中心安装"
echo "══════════════════════════════════════════"
echo ""

# ---------------------------------------------------
# 1. Check Python
# ---------------------------------------------------
echo -n "  检测 Python 3... "
if command -v python3 &>/dev/null; then
    PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        info "Python ${PY_VERSION} ✓"
    else
        error "Python ${PY_VERSION} 版本过低，需要 3.10+"
        echo "  请运行: apt install python3.11 python3.11-venv"
        exit 1
    fi
else
    error "未找到 python3"
    echo "  请运行: apt install python3 python3-venv python3-pip"
    exit 1
fi

# Ensure python3-venv is installed (--help can succeed even without ensurepip)
VENV_PKG="python3.${PY_MINOR}-venv"
if ! dpkg -s "${VENV_PKG}" &>/dev/null 2>&1; then
    warn "缺少 ${VENV_PKG}，正在安装..."
    apt-get update -qq && apt-get install -y -qq "${VENV_PKG}"
    info "${VENV_PKG} 已安装"
fi

# ---------------------------------------------------
# 2. Create directories
# ---------------------------------------------------
echo -n "  创建目录... "
mkdir -p "${DATA_DIR}"
mkdir -p "${BACKUP_DIR}"
info "完成"

# ---------------------------------------------------
# 3. Create virtual environment
# ---------------------------------------------------
echo -n "  创建 Python 虚拟环境... "
if [ ! -d "${VENV_DIR}" ]; then
    python3 -m venv "${VENV_DIR}"
    info "完成"
else
    info "已存在"
fi

# ---------------------------------------------------
# 4. Install dependencies
# ---------------------------------------------------
echo -n "  安装 Python 依赖... "
"${VENV_DIR}/bin/pip" install --quiet --upgrade pip
"${VENV_DIR}/bin/pip" install --quiet -r "${APP_DIR}/controller/requirements.txt"
info "完成"

# ---------------------------------------------------
# 5. Generate SSH key pair
# ---------------------------------------------------
echo -n "  生成 SSH 密钥对... "
if [ ! -f "${SSH_KEY}" ]; then
    ssh-keygen -t ed25519 -f "${SSH_KEY}" -N "" -C "snell-manager" -q
    info "已生成 ${SSH_KEY}"
else
    info "已存在"
fi

# ---------------------------------------------------
# 6. Initialize database
# ---------------------------------------------------
echo -n "  初始化数据库... "
SNELL_DB="${DATA_DIR}/snell_manager.db" \
SNELL_CONFIG="${APP_DIR}/controller/config.yaml" \
"${VENV_DIR}/bin/python" -c "
import asyncio
import sys
sys.path.insert(0, '${APP_DIR}/controller')
from app.database import init_db
asyncio.run(init_db())
print('ok')
" 2>/dev/null
info "完成"

# ---------------------------------------------------
# 7. Install systemd service
# ---------------------------------------------------
echo -n "  安装 systemd 服务... "
cat > /etc/systemd/system/${SERVICE_NAME}.service << SYSTEMD_EOF
[Unit]
Description=Snell UFW Manager
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${APP_DIR}/controller
Environment=SNELL_DB=${DATA_DIR}/snell_manager.db
Environment=SNELL_CONFIG=${APP_DIR}/controller/config.yaml
ExecStart=${VENV_DIR}/bin/uvicorn app.main:app --host 127.0.0.1 --port 8899 --workers 1
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
SYSTEMD_EOF

systemctl daemon-reload
systemctl enable ${SERVICE_NAME} --quiet
info "完成"

# ---------------------------------------------------
# 8. Start service
# ---------------------------------------------------
echo -n "  启动服务... "
systemctl restart ${SERVICE_NAME}
sleep 2
if systemctl is-active --quiet ${SERVICE_NAME}; then
    info "运行中"
else
    error "启动失败，请检查: journalctl -u ${SERVICE_NAME} -n 20"
    exit 1
fi

# ---------------------------------------------------
# Done
# ---------------------------------------------------
# Get the machine's IP for display
MACHINE_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "<本机IP>")

echo ""
echo "══════════════════════════════════════════"
echo -e " ${GREEN}✅ Snell UFW Manager 已启动${NC}"
echo ""
echo " 在本地执行以下命令访问面板："
echo -e "   ${YELLOW}ssh -L 8899:127.0.0.1:8899 root@${MACHINE_IP}${NC}"
echo ""
echo " 然后浏览器打开："
echo -e "   ${YELLOW}http://localhost:8899${NC}"
echo ""
echo " SSH 公钥（用于节点初始化）："
echo -e "   ${YELLOW}$(cat ${SSH_KEY}.pub)${NC}"
echo ""
echo " 常用命令："
echo "   查看状态: systemctl status ${SERVICE_NAME}"
echo "   查看日志: journalctl -u ${SERVICE_NAME} -f"
echo "   重启服务: systemctl restart ${SERVICE_NAME}"
echo "══════════════════════════════════════════"
echo ""
