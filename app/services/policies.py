from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Node, NodePolicy
from app.schemas import NodePolicyCreate
from app.services.ufw_parser import ManagedUFWComment


def enabled_protocols(node: Node) -> list[str]:
    protocols: list[str] = []
    if node.enable_tcp:
        protocols.append("tcp")
    if node.enable_udp:
        protocols.append("udp")
    return protocols


def build_ufw_apply_payload(node: Node) -> dict[str, Any]:
    protocols = enabled_protocols(node)
    rules: list[dict[str, Any]] = []
    for policy in node.policies:
        if not policy.enabled:
            continue
        relay_group = policy.relay_group
        for relay_ip in relay_group.relay_ips:
            for proto in protocols:
                comment = ManagedUFWComment(
                    node_id=int(node.id),
                    group_id=int(relay_group.id),
                    port=int(node.snell_port),
                    proto=proto,
                )
                rules.append(
                    {
                        "group_id": int(relay_group.id),
                        "source": relay_ip.value,
                        "proto": proto,
                        "comment": str(comment),
                    }
                )

    return {
        "node_id": int(node.id),
        "port": int(node.snell_port),
        "protocols": protocols,
        "rules": rules,
    }


def list_policies(db: Session) -> list[NodePolicy]:
    return list(
        db.scalars(
            select(NodePolicy)
            .options(
                selectinload(NodePolicy.node).selectinload(Node.policies),
                selectinload(NodePolicy.relay_group),
            )
            .order_by(NodePolicy.id)
        )
    )


def create_policy(db: Session, data: NodePolicyCreate) -> NodePolicy:
    policy = NodePolicy(**data.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy
