from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import RelayGroup, RelayIP
from app.schemas import RelayGroupCreate, RelayIPCreate


def list_relay_groups(db: Session) -> list[RelayGroup]:
    return list(
        db.scalars(
            select(RelayGroup)
            .options(selectinload(RelayGroup.relay_ips))
            .order_by(RelayGroup.id)
        )
    )


def create_relay_group(db: Session, data: RelayGroupCreate) -> RelayGroup:
    group = RelayGroup(**data.model_dump())
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


def update_relay_group(db: Session, group_id: int, data: RelayGroupCreate) -> RelayGroup:
    group = db.get(RelayGroup, group_id)
    if group is None:
        raise ValueError("relay group not found")
    group.name = data.name
    group.remark = data.remark
    db.commit()
    db.refresh(group)
    return group


def delete_relay_group(db: Session, group_id: int) -> RelayGroup:
    group = db.get(RelayGroup, group_id)
    if group is None:
        raise ValueError("relay group not found")
    db.delete(group)
    db.commit()
    return group


def add_relay_ip(db: Session, data: RelayIPCreate) -> RelayIP:
    relay_ip = RelayIP(**data.model_dump())
    db.add(relay_ip)
    db.commit()
    db.refresh(relay_ip)
    return relay_ip


def delete_relay_ip(db: Session, relay_ip_id: int) -> RelayIP:
    relay_ip = db.get(RelayIP, relay_ip_id)
    if relay_ip is None:
        raise ValueError("relay IP not found")
    db.delete(relay_ip)
    db.commit()
    return relay_ip
