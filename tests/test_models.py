from __future__ import annotations

from datetime import datetime, timezone

from app.db import Base
from app.models import (
    AccessCandidate,
    AuditLog,
    Node,
    NodePolicy,
    OperationLock,
    RelayGroup,
    RelayIP,
    SnellConfigProfile,
)


def test_all_expected_tables_are_registered() -> None:
    assert {
        "nodes",
        "snell_config_profiles",
        "relay_groups",
        "relay_ips",
        "node_policies",
        "access_candidates",
        "audit_logs",
        "operation_locks",
    }.issubset(Base.metadata.tables.keys())


def test_valid_model_graph_can_be_created() -> None:
    node = Node(
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=22,
        ssh_user="snellmgr",
        snell_port=23456,
        enable_tcp=True,
        enable_udp=True,
        psk="shared-secret",
        desired_config_text="listen = ::0:23456\npsk = shared-secret\n",
    )
    profile = SnellConfigProfile(
        name="default-v5",
        snell_port=23456,
        snell_version="v5.x",
        snell_channel="stable",
        snell_arch="amd64",
        enable_tcp=True,
        enable_udp=True,
        psk="shared-secret",
        config_text="listen = ::0:23456\npsk = shared-secret\n",
    )
    group = RelayGroup(name="relay-a", remark="primary relay")
    relay_ip = RelayIP(relay_group=group, value="198.51.100.0/24")
    policy = NodePolicy(node=node, relay_group=group, enabled=True)
    candidate = AccessCandidate(
        node=node,
        ip="198.51.100.8",
        port=23456,
        protocol="udp",
        source="ufw",
        hit_count=3,
    )
    audit = AuditLog(
        actor="admin",
        action="node.create",
        target_type="node",
        summary="created node",
        request_json={"name": "Tokyo 1"},
        result_json={"ok": True},
        success=True,
    )
    lock = OperationLock(
        node=node,
        operation_type="ufw apply",
        owner="test",
        locked_at=datetime.now(timezone.utc),
    )

    assert node.name == "Tokyo 1"
    assert profile.snell_version == "v5.x"
    assert relay_ip.relay_group is group
    assert policy.node is node
    assert candidate.protocol == "udp"
    assert audit.success is True
    assert lock.node is node
