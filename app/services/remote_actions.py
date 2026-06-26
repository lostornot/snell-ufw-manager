from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session, selectinload

from app.models import Node
from app.schemas import NodeCreate
from app.services.audit import write_audit
from app.services.candidates import upsert_candidate
from app.services.policies import build_ufw_apply_payload
from app.services.ssh_executor import SSHCommandResult, run_remote_command


def _get_node(db: Session, node_id: int) -> Node:
    node = db.get(
        Node,
        node_id,
        options=[
            selectinload(Node.policies),
        ],
    )
    if node is None:
        raise ValueError(f"node not found: {node_id}")
    return node


def _node_payload(node: Node) -> NodeCreate:
    return NodeCreate(
        name=node.name,
        host=node.host,
        ssh_alias=node.ssh_alias,
        ssh_port=node.ssh_port,
        ssh_user=node.ssh_user,
        ssh_key_path=node.ssh_key_path,
        connect_timeout=node.connect_timeout,
        snell_port=node.snell_port,
        snell_version=node.snell_version,
        snell_channel=node.snell_channel,
        snell_arch=node.snell_arch,
        enable_tcp=node.enable_tcp,
        enable_udp=node.enable_udp,
        remark=node.remark,
        enabled=node.enabled,
        desired_config_text=node.desired_config_text,
        psk=node.psk,
    )


def _result_body(result: SSHCommandResult) -> dict[str, Any]:
    if result.timed_out:
        return {
            "ok": False,
            "data": {},
            "error": {"code": "SSH_TIMEOUT", "message": "remote command timed out"},
        }
    if isinstance(result.parsed_json, dict):
        return result.parsed_json
    return {
        "ok": False,
        "data": {},
        "error": {
            "code": "SSH_INVALID_JSON",
            "message": result.json_error or "remote command did not return JSON",
        },
    }


def _audit_remote(
    db: Session,
    *,
    action: str,
    node: Node,
    request_json: dict[str, Any],
    result: dict[str, Any],
) -> None:
    error = result.get("error")
    write_audit(
        db,
        actor="admin",
        action=action,
        target_type="node",
        target_id=node.id,
        summary=f"{action} for {node.name}",
        request_json=request_json,
        result_json=result,
        success=bool(result.get("ok")),
        error=error.get("message") if isinstance(error, dict) else None,
    )


def refresh_node_status(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"dry_run": False}
    result = _result_body(run_remote_command(_node_payload(node), "snell", "status", payload))
    if result.get("ok"):
        data = result.get("data", {})
        node.last_status = data.get("status")
        node.last_error = None
    else:
        error = result.get("error")
        node.last_error = error.get("message") if isinstance(error, dict) else "status failed"
    _audit_remote(db, action="node.status", node=node, request_json=payload, result=result)
    db.commit()
    return result


def refresh_ufw_list(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"port": node.snell_port, "node_id": node.id}
    result = _result_body(run_remote_command(_node_payload(node), "ufw", "list", payload))
    _audit_remote(db, action="ufw.list", node=node, request_json=payload, result=result)
    return result


def check_node_environment(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"node_id": node.id}
    result = _result_body(run_remote_command(_node_payload(node), "system", "check", payload))
    _audit_remote(db, action="node.check", node=node, request_json=payload, result=result)
    return result


def apply_ufw_policy(db: Session, node_id: int) -> dict[str, Any]:
    node = (
        db.query(Node)
        .options(
            selectinload(Node.policies),
        )
        .filter(Node.id == node_id)
        .one_or_none()
    )
    if node is None:
        raise ValueError(f"node not found: {node_id}")
    for policy in node.policies:
        _ = policy.relay_group.relay_ips
    payload = build_ufw_apply_payload(node)
    result = _result_body(run_remote_command(_node_payload(node), "ufw", "apply", payload))
    _audit_remote(db, action="ufw.apply", node=node, request_json=payload, result=result)
    return result


def apply_snell_config(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {
        "snell_version": node.snell_version,
        "snell_channel": node.snell_channel,
        "snell_arch": node.snell_arch,
        "port": node.snell_port,
        "enable_tcp": node.enable_tcp,
        "enable_udp": node.enable_udp,
        "psk": node.psk,
        "config_text": node.desired_config_text,
    }
    result = _result_body(run_remote_command(_node_payload(node), "snell", "config-apply", payload))
    _audit_remote(db, action="snell.config_apply", node=node, request_json=payload, result=result)
    return result


def install_snell(
    db: Session,
    node_id: int,
    *,
    custom_binary_path: str | None = None,
    snell_download_url: str | None = None,
) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {
        "snell_version": node.snell_version,
        "snell_channel": node.snell_channel,
        "snell_arch": node.snell_arch,
        "port": node.snell_port,
        "enable_tcp": node.enable_tcp,
        "enable_udp": node.enable_udp,
        "psk": node.psk,
        "config_text": node.desired_config_text,
        "custom_binary_path": custom_binary_path,
        "snell_download_url": snell_download_url,
    }
    result = _result_body(run_remote_command(_node_payload(node), "snell", "install", payload))
    _audit_remote(db, action="snell.install", node=node, request_json=payload, result=result)
    return result


def run_snell_service_action(db: Session, node_id: int, action: str) -> dict[str, Any]:
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"unsupported service action: {action}")
    node = _get_node(db, node_id)
    payload = {"service_name": "snell"}
    result = _result_body(run_remote_command(_node_payload(node), "snell", action, payload))
    _audit_remote(db, action=f"snell.{action}", node=node, request_json=payload, result=result)
    return result


def get_snell_config(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload: dict[str, Any] = {}
    result = _result_body(run_remote_command(_node_payload(node), "snell", "config-get", payload))
    _audit_remote(db, action="snell.config_get", node=node, request_json=payload, result=result)
    return result


def read_snell_logs(db: Session, node_id: int, *, lines: int = 100) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"lines": lines}
    result = _result_body(run_remote_command(_node_payload(node), "snell", "logs", payload))
    _audit_remote(db, action="snell.logs", node=node, request_json=payload, result=result)
    return result


def restore_snell_config(db: Session, node_id: int, backup_path: str) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"backup_path": backup_path}
    result = _result_body(run_remote_command(_node_payload(node), "snell", "restore", payload))
    _audit_remote(db, action="snell.restore", node=node, request_json=payload, result=result)
    return result


def refresh_access_candidates(db: Session, node_id: int) -> dict[str, Any]:
    node = _get_node(db, node_id)
    payload = {"node_id": node.id, "port": node.snell_port}
    result = _result_body(run_remote_command(_node_payload(node), "ufw", "candidates", payload))
    if result.get("ok"):
        for candidate in result.get("data", {}).get("candidates", []):
            upsert_candidate(
                db,
                node_id=node.id,
                ip=candidate["ip"],
                port=int(candidate.get("port", node.snell_port)),
                protocol=candidate.get("protocol", "tcp"),
                source=candidate.get("source", "unknown"),
            )
    _audit_remote(db, action="ufw.candidates", node=node, request_json=payload, result=result)
    return result | {"promoted_count": 0}
