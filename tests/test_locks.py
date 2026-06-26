from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.locks import acquire_operation_lock, is_write_operation, release_operation_lock
from app.models import Node


def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def create_node(db: Session) -> Node:
    node = Node(
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=22,
        ssh_user="snellmgr",
        snell_port=23456,
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def test_write_operations_are_classified() -> None:
    assert is_write_operation("ufw apply") is True
    assert is_write_operation("snell restart") is True
    assert is_write_operation("ufw list") is False
    assert is_write_operation("snell status") is False


def test_only_one_write_operation_lock_per_node() -> None:
    db = session()
    node = create_node(db)

    first = acquire_operation_lock(db, node_id=node.id, operation_type="ufw apply", owner="a")
    second = acquire_operation_lock(db, node_id=node.id, operation_type="snell restart", owner="b")

    assert first is True
    assert second is False


def test_lock_can_be_released() -> None:
    db = session()
    node = create_node(db)

    assert acquire_operation_lock(db, node_id=node.id, operation_type="ufw apply", owner="a") is True
    release_operation_lock(db, node_id=node.id)

    assert acquire_operation_lock(db, node_id=node.id, operation_type="ufw apply", owner="b") is True

