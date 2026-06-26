#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/snell-ufw-control}"
SERVICE_NAME="snell-ufw-control.service"
BIND_HOST="${BIND_HOST:-127.0.0.1}"
BIND_PORT="${BIND_PORT:-8898}"

install -d -m 0755 "$APP_DIR"
install -d -m 700 "$APP_DIR/data"
chmod 700 "$APP_DIR/data"

if [[ ! -f "$APP_DIR/.env" ]]; then
  ADMIN_TOKEN="$(python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(32))
PY
)"
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
    printf 'ADMIN_TOKEN=%s\n' "$ADMIN_TOKEN"
    printf 'SESSION_SECRET=%s\n' "$SESSION_SECRET"
  } > "$APP_DIR/.env"
  chmod 600 "$APP_DIR/.env"
fi

if [[ -f "$APP_DIR/data/snell-ufw-control.db" ]]; then
  chmod 600 "$APP_DIR/data/snell-ufw-control.db"
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install "$APP_DIR"

install -d -m 0755 /etc/systemd/system
install -m 0644 "systemd/$SERVICE_NAME" "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME"

printf 'Controller installed. Access it through SSH Tunnel at http://%s:%s\n' "$BIND_HOST" "$BIND_PORT"
printf 'ADMIN_TOKEN is stored in %s/.env\n' "$APP_DIR"
