from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Node, SnellConfigProfile
from app.schemas import NodeCreate, SnellConfigProfileCreate


def ensure_pinned_snell_version(version: str | None) -> str:
    if version is None or not version.strip() or version.strip().lower() == "latest":
        raise ValueError("Snell version must be explicit; do not use latest")
    return version


def render_snell_config(*, snell_port: int, psk: str, extra_config: str | None = None) -> str:
    lines = [
        f"listen = ::0:{snell_port}",
        f"psk = {psk}",
    ]
    if extra_config:
        lines.append(extra_config.rstrip())
    return "\n".join(lines) + "\n"


def list_nodes(db: Session) -> list[Node]:
    return list(db.scalars(select(Node).order_by(Node.id)))


def create_node(db: Session, data: NodeCreate) -> Node:
    node = Node(**data.model_dump())
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def update_node(db: Session, node_id: int, data: NodeCreate) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise ValueError("node not found")
    for key, value in data.model_dump().items():
        setattr(node, key, value)
    db.commit()
    db.refresh(node)
    return node


def update_node_config(
    db: Session,
    node_id: int,
    *,
    desired_config_text: str | None,
    psk: str | None,
    snell_version: str | None,
) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise ValueError("node not found")
    node.desired_config_text = desired_config_text
    node.psk = psk
    node.snell_version = snell_version
    db.commit()
    db.refresh(node)
    return node


def delete_node(db: Session, node_id: int) -> Node:
    node = db.get(Node, node_id)
    if node is None:
        raise ValueError("node not found")
    db.delete(node)
    db.commit()
    return node


def list_profiles(db: Session) -> list[SnellConfigProfile]:
    return list(db.scalars(select(SnellConfigProfile).order_by(SnellConfigProfile.id)))


def create_profile(db: Session, data: SnellConfigProfileCreate) -> SnellConfigProfile:
    profile = SnellConfigProfile(**data.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile
