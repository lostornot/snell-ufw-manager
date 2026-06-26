from __future__ import annotations

from app.models import Node, NodePolicy, RelayGroup, RelayIP
from app.services.policies import build_ufw_apply_payload


def test_builds_tcp_and_udp_policy_payload_from_enabled_groups() -> None:
    node = Node(
        id=10,
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=22,
        ssh_user="snellmgr",
        snell_port=23456,
        enable_tcp=True,
        enable_udp=True,
    )
    group = RelayGroup(id=3, name="relay-a")
    group.relay_ips = [
        RelayIP(id=1, relay_group_id=3, value="198.51.100.8"),
        RelayIP(id=2, relay_group_id=3, value="198.51.100.0/24"),
    ]
    node.policies = [NodePolicy(node=node, relay_group=group, enabled=True)]

    payload = build_ufw_apply_payload(node)

    assert payload == {
        "node_id": 10,
        "port": 23456,
        "protocols": ["tcp", "udp"],
        "rules": [
            {
                "group_id": 3,
                "source": "198.51.100.8",
                "proto": "tcp",
                "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
            },
            {
                "group_id": 3,
                "source": "198.51.100.8",
                "proto": "udp",
                "comment": "snell-control:node:10:group:3:port:23456:proto:udp",
            },
            {
                "group_id": 3,
                "source": "198.51.100.0/24",
                "proto": "tcp",
                "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
            },
            {
                "group_id": 3,
                "source": "198.51.100.0/24",
                "proto": "udp",
                "comment": "snell-control:node:10:group:3:port:23456:proto:udp",
            },
        ],
    }


def test_disabled_policy_is_not_in_payload() -> None:
    node = Node(
        id=10,
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=22,
        ssh_user="snellmgr",
        snell_port=23456,
        enable_tcp=True,
        enable_udp=False,
    )
    group = RelayGroup(id=3, name="relay-a")
    group.relay_ips = [RelayIP(id=1, relay_group_id=3, value="198.51.100.8")]
    node.policies = [NodePolicy(node=node, relay_group=group, enabled=False)]

    payload = build_ufw_apply_payload(node)

    assert payload["protocols"] == ["tcp"]
    assert payload["rules"] == []

