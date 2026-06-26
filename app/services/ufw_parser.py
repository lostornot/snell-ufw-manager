from __future__ import annotations

import re
from dataclasses import dataclass

MANAGED_COMMENT_RE = re.compile(
    r"^snell-control:node:(?P<node_id>\d+):group:(?P<group_id>\d+):"
    r"port:(?P<port>\d+):proto:(?P<proto>tcp|udp)$"
)


@dataclass(frozen=True)
class ManagedUFWComment:
    node_id: int
    group_id: int
    port: int
    proto: str

    def __str__(self) -> str:
        return (
            f"snell-control:node:{self.node_id}:group:{self.group_id}:"
            f"port:{self.port}:proto:{self.proto}"
        )


def parse_managed_comment(comment: str) -> ManagedUFWComment | None:
    match = MANAGED_COMMENT_RE.fullmatch(comment.strip())
    if not match:
        return None
    return ManagedUFWComment(
        node_id=int(match.group("node_id")),
        group_id=int(match.group("group_id")),
        port=int(match.group("port")),
        proto=match.group("proto"),
    )

