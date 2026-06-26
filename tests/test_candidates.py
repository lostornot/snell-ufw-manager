from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.models import Node, RelayGroup
from app.services.candidates import promote_candidate, upsert_candidate


def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def create_node_and_group(db: Session) -> tuple[Node, RelayGroup]:
    node = Node(
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=22,
        ssh_user="snellmgr",
        snell_port=23456,
    )
    group = RelayGroup(name="relay-a")
    db.add_all([node, group])
    db.commit()
    db.refresh(node)
    db.refresh(group)
    return node, group


def test_upsert_candidate_increments_hit_count() -> None:
    db = session()
    node, _ = create_node_and_group(db)

    first = upsert_candidate(db, node_id=node.id, ip="198.51.100.8", port=23456, protocol="tcp", source="ufw")
    second = upsert_candidate(db, node_id=node.id, ip="198.51.100.8", port=23456, protocol="tcp", source="ufw")

    assert first.id == second.id
    assert second.hit_count == 2


def test_promote_candidate_requires_confirmation() -> None:
    db = session()
    node, group = create_node_and_group(db)
    candidate = upsert_candidate(db, node_id=node.id, ip="198.51.100.8", port=23456, protocol="tcp", source="ufw")

    with pytest.raises(ValueError):
        promote_candidate(db, candidate_id=candidate.id, relay_group_id=group.id, confirmed=False)


def test_promote_candidate_adds_relay_ip_and_marks_candidate() -> None:
    db = session()
    node, group = create_node_and_group(db)
    candidate = upsert_candidate(db, node_id=node.id, ip="198.51.100.8", port=23456, protocol="tcp", source="ufw")

    relay_ip = promote_candidate(db, candidate_id=candidate.id, relay_group_id=group.id, confirmed=True)

    db.refresh(candidate)
    assert relay_ip.value == "198.51.100.8"
    assert relay_ip.relay_group_id == group.id
    assert candidate.promoted is True
    assert candidate.promoted_relay_group_id == group.id

