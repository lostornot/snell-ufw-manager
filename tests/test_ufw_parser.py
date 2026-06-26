from __future__ import annotations

from app.services.ufw_parser import (
    ManagedUFWComment,
    parse_managed_comment,
)


def test_parses_managed_comment_with_port_and_proto() -> None:
    parsed = parse_managed_comment("snell-control:node:7:group:3:port:23456:proto:udp")

    assert parsed == ManagedUFWComment(node_id=7, group_id=3, port=23456, proto="udp")


def test_rejects_unmanaged_comment() -> None:
    assert parse_managed_comment("allow snell") is None
    assert parse_managed_comment("snell-control:node:7:group:3:proto:tcp") is None


def test_managed_comment_renders_canonical_string() -> None:
    comment = ManagedUFWComment(node_id=7, group_id=3, port=23456, proto="tcp")

    assert str(comment) == "snell-control:node:7:group:3:port:23456:proto:tcp"

