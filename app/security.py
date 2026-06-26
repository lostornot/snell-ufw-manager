from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from typing import Any

from fastapi import Form, HTTPException, Request, status

from app.config import Settings

SESSION_COOKIE = "snell_session"


def _sign(value: str, secret: str) -> str:
    return hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def encode_session(payload: dict[str, Any], secret: str) -> str:
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    ).decode()
    return f"{encoded}.{_sign(encoded, secret)}"


def decode_session(cookie_value: str | None, secret: str) -> dict[str, Any] | None:
    if not cookie_value or "." not in cookie_value:
        return None
    encoded, signature = cookie_value.rsplit(".", 1)
    if not hmac.compare_digest(_sign(encoded, secret), signature):
        return None
    try:
        decoded = base64.urlsafe_b64decode(encoded.encode()).decode()
        data = json.loads(decoded)
    except (ValueError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def session_secret(settings: Settings) -> str:
    return settings.session_secret or "dev-session-secret-change-me"


def admin_token(settings: Settings) -> str:
    return settings.admin_token or "dev-admin-token-change-me"


def create_session_cookie(settings: Settings) -> tuple[str, str]:
    csrf_token = secrets.token_urlsafe(32)
    cookie = encode_session({"authenticated": True, "csrf_token": csrf_token}, session_secret(settings))
    return cookie, csrf_token


def get_session(request: Request) -> dict[str, Any] | None:
    settings: Settings = request.app.state.settings
    return decode_session(request.cookies.get(SESSION_COOKIE), session_secret(settings))


def require_session(request: Request) -> dict[str, Any]:
    session = get_session(request)
    if not session or session.get("authenticated") is not True:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED)
    return session


def verify_csrf(request: Request, csrf_token: str = Form(default="")) -> None:
    session = require_session(request)
    expected = session.get("csrf_token")
    if not expected or not hmac.compare_digest(str(expected), csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid csrf token")

