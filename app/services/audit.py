from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog

SENSITIVE_KEYS = {
    "psk",
    "password",
    "private_key",
    "config_text",
    "desired_config_text",
}
REDACTED = "********"


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[Any, Any] = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SENSITIVE_KEYS or "secret" in key_text or "token" in key_text:
                redacted[key] = REDACTED
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        lines = value.splitlines()
        if lines and any("psk" in line.lower() for line in lines):
            masked = [line.split("=", 1)[0].rstrip() + " = " + REDACTED if "psk" in line.lower() else line for line in lines]
            return "\n".join(masked)
        return value
    return value


def write_audit(
    db: Session,
    *,
    actor: str,
    action: str,
    summary: str,
    success: bool,
    target_type: str | None = None,
    target_id: int | None = None,
    request_json: dict[str, Any] | list[Any] | None = None,
    result_json: dict[str, Any] | list[Any] | None = None,
    error: str | None = None,
) -> AuditLog:
    audit = AuditLog(
        actor=actor,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        request_json=redact_sensitive(request_json),
        result_json=redact_sensitive(result_json),
        success=success,
        error=error,
    )
    db.add(audit)
    db.commit()
    db.refresh(audit)
    return audit
