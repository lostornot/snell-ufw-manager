#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/snell-ufw-manager-by-gpt}"
SERVICE_NAME="snell-ufw-control.service"
SERVICE_USER="${SERVICE_USER:-snell-ufw-control}"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
BIND_PORT="${BIND_PORT:-8898}"
SOURCE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$SOURCE_DIR/pyproject.toml" ]]; then
  printf 'ERROR: %s does not look like the project root; pyproject.toml not found.\n' "$SOURCE_DIR" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

install -d -m 0755 "$APP_DIR"
install -d -m 700 "$APP_DIR/data"
install -d -m 700 "$APP_DIR/.ssh"
chmod 700 "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data"
chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/.ssh"

if command -v rsync >/dev/null 2>&1; then
  rsync -a --delete \
    --exclude=.git \
    --exclude=.venv \
    --exclude=.pytest_cache \
    --exclude='*.egg-info' \
    --exclude='__pycache__' \
    --exclude=.DS_Store \
    --exclude=.env \
    --exclude=data \
    "$SOURCE_DIR/" "$APP_DIR/"
else
  tar -C "$SOURCE_DIR" \
    --exclude=.git \
    --exclude=.venv \
    --exclude=.pytest_cache \
    --exclude='*.egg-info' \
    --exclude='__pycache__' \
    --exclude=.DS_Store \
    --exclude=.env \
    --exclude=data \
    -cf - . | tar -C "$APP_DIR" -xf -
fi

if [[ ! -f "$APP_DIR/.env" ]]; then
  SESSION_SECRET="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
)"
  umask 077
  {
    printf 'HOST=%s\n' "$BIND_HOST"
    printf 'PORT=%s\n' "$BIND_PORT"
    printf 'DATA_DIR=%s\n' "$APP_DIR/data"
    printf 'DATABASE_URL=sqlite:///%s/data/snell-ufw-control.db\n' "$APP_DIR"
    printf 'SESSION_SECRET=%s\n' "$SESSION_SECRET"
  } > "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

chown root:root "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"

if [[ -f "$APP_DIR/data/snell-ufw-control.db" ]]; then
  chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR/data/snell-ufw-control.db"
  chmod 600 "$APP_DIR/data/snell-ufw-control.db"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install "$APP_DIR"

install -d -m 0755 /etc/systemd/system
install -m 0644 "$APP_DIR/systemd/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

printf 'Controller installed. Access it through SSH Tunnel at http://%s:%s\n' "$BIND_HOST" "$BIND_PORT"
printf 'SESSION_SECRET is stored in %s/.env\n' "$APP_DIR"
