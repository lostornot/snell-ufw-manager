from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessCandidate, RelayIP


def upsert_candidate(
    db: Session,
    *,
    node_id: int,
    ip: str,
    port: int,
    protocol: str,
    source: str,
) -> AccessCandidate:
    candidate = db.scalars(
        select(AccessCandidate).where(
            AccessCandidate.node_id == node_id,
            AccessCandidate.ip == ip,
            AccessCandidate.port == port,
            AccessCandidate.protocol == protocol,
            AccessCandidate.source == source,
        )
    ).first()
    now = datetime.now(timezone.utc)
    if candidate is None:
        candidate = AccessCandidate(
            node_id=node_id,
            ip=ip,
            port=port,
            protocol=protocol,
            source=source,
            hit_count=1,
            first_seen_at=now,
            last_seen_at=now,
        )
        db.add(candidate)
    else:
        candidate.hit_count += 1
        candidate.last_seen_at = now

    db.commit()
    db.refresh(candidate)
    return candidate


def promote_candidate(
    db: Session,
    *,
    candidate_id: int,
    relay_group_id: int,
    confirmed: bool,
) -> RelayIP:
    if not confirmed:
        raise ValueError("candidate promotion requires confirmation")

    candidate = db.get(AccessCandidate, candidate_id)
    if candidate is None:
        raise ValueError("candidate not found")

    relay_ip = RelayIP(relay_group_id=relay_group_id, value=candidate.ip)
    candidate.promoted = True
    candidate.promoted_relay_group_id = relay_group_id
    db.add(relay_ip)
    db.commit()
    db.refresh(relay_ip)
    db.refresh(candidate)
    return relay_ip
