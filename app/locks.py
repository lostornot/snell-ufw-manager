from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.models import OperationLock

WRITE_OPERATIONS = {
    "snell install",
    "snell config-apply",
    "snell start",
    "snell stop",
    "snell restart",
    "snell restore",
    "ufw apply",
    "ufw restore",
    "ufw enable",
}


def is_write_operation(operation_type: str) -> bool:
    return operation_type in WRITE_OPERATIONS


def acquire_operation_lock(
    db: Session,
    *,
    node_id: int,
    operation_type: str,
    owner: str,
    ttl_seconds: int = 600,
) -> bool:
    if not is_write_operation(operation_type):
        return True

    existing = db.get(OperationLock, node_id)
    if existing is not None:
        return False

    now = datetime.now(UTC)
    db.add(
        OperationLock(
            node_id=node_id,
            operation_type=operation_type,
            owner=owner,
            locked_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
    )
    db.commit()
    return True


def release_operation_lock(db: Session, *, node_id: int) -> None:
    existing = db.get(OperationLock, node_id)
    if existing is None:
        return
    db.delete(existing)
    db.commit()

