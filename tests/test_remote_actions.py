from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.locks import acquire_operation_lock
from app.models import AuditLog, Node, RelayGroup, RelayIP, NodePolicy, OperationLock
from app.services import remote_actions
from app.services.remote_actions import (
    check_node_environment,
    get_snell_config,
    install_snell,
    read_snell_logs,
    apply_snell_config,
    apply_ufw_policy,
    enable_ufw,
    refresh_access_candidates,
    refresh_node_status,
    refresh_ufw_list,
    restore_snell_config,
    run_snell_service_action,
)
from app.services.ssh_executor import SSHCommandResult


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
        snell_version="v5.x",
        snell_arch="amd64",
        enable_tcp=True,
        enable_udp=True,
        desired_config_text="listen = ::0:23456\npsk = secret\n",
        psk="secret",
    )
    db.add(node)
    db.commit()
    db.refresh(node)
    return node


def ok_result(data: dict) -> SSHCommandResult:
    return SSHCommandResult(
        returncode=0,
        stdout="{}",
        stderr="",
        parsed_json={"ok": True, "data": data, "error": None},
    )


def test_refresh_node_status_updates_node_and_audit(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    calls = []

    def fake_run(node_payload, namespace, subcommand, payload):
        calls.append((node_payload, namespace, subcommand, payload))
        return ok_result({"status": "running", "version": "v5.x", "port": 23456})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = refresh_node_status(db, node.id)

    db.refresh(node)
    audit = db.query(AuditLog).one()
    assert result["ok"] is True
    assert calls[0][1:] == ("snell", "status", {"dry_run": False})
    assert node.last_status == "running"
    assert node.last_error is None
    assert audit.action == "node.status"
    assert audit.success is True


def test_refresh_ufw_list_returns_remote_data_and_audits(monkeypatch) -> None:
    db = session()
    node = create_node(db)

    def fake_run(node_payload, namespace, subcommand, payload):
        assert namespace == "ufw"
        assert subcommand == "list"
        assert payload == {"port": 23456, "node_id": node.id}
        return ok_result({"active": False, "warnings": ["UFW inactive"]})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = refresh_ufw_list(db, node.id)

    assert result["data"]["active"] is False
    assert db.query(AuditLog).one().action == "ufw.list"


def test_check_node_environment_returns_remote_data_and_audits(monkeypatch) -> None:
    db = session()
    node = create_node(db)

    def fake_run(node_payload, namespace, subcommand, payload):
        assert namespace == "system"
        assert subcommand == "check"
        assert payload == {"node_id": node.id}
        return ok_result(
            {
                "snell_fwctl": {"present": True},
                "snellctl": {"present": True},
                "ufwctl": {"present": True},
                "ufw": {"active": False},
            }
        )

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = check_node_environment(db, node.id)

    db.refresh(node)
    assert result["data"]["snell_fwctl"]["present"] is True
    assert node.last_seen_at is not None
    assert node.last_error is None
    assert db.query(AuditLog).one().action == "node.check"


def test_apply_ufw_policy_uses_policy_payload(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    group = RelayGroup(name="relay-a")
    db.add(group)
    db.commit()
    db.refresh(group)
    db.add(RelayIP(relay_group_id=group.id, value="198.51.100.8"))
    db.add(NodePolicy(node_id=node.id, relay_group_id=group.id, enabled=True))
    db.commit()
    captured = {}

    def fake_run(node_payload, namespace, subcommand, payload):
        captured["namespace"] = namespace
        captured["subcommand"] = subcommand
        captured["payload"] = payload
        return ok_result({"active": True, "applied": True})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = apply_ufw_policy(db, node.id)

    assert result["ok"] is True
    assert captured["namespace"] == "ufw"
    assert captured["subcommand"] == "apply"
    assert captured["payload"]["rules"][0]["source"] == "198.51.100.8"
    assert captured["payload"]["rules"][0]["comment"] == "snell-control:node:1:group:1:port:23456:proto:tcp"
    assert db.query(AuditLog).one().action == "ufw.apply"
    assert db.get(OperationLock, node.id) is None


def test_write_operation_conflict_is_audited_without_remote_call(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    assert acquire_operation_lock(db, node_id=node.id, operation_type="ufw apply", owner="other") is True

    def fake_run(node_payload, namespace, subcommand, payload):
        raise AssertionError("remote command should not run while node is locked")

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = apply_ufw_policy(db, node.id)

    audit = db.query(AuditLog).one()
    assert result["ok"] is False
    assert result["error"]["code"] == "NODE_OPERATION_LOCKED"
    assert audit.action == "ufw.apply"
    assert audit.success is False
    assert db.get(OperationLock, node.id) is not None


def test_enable_ufw_uses_danger_confirmation_payload_and_lock(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    captured = {}

    def fake_run(node_payload, namespace, subcommand, payload):
        captured.update(namespace=namespace, subcommand=subcommand, payload=payload)
        return ok_result({"would_enable": True})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = enable_ufw(db, node.id, emergency_ssh_cidr="203.0.113.0/24", confirmed=True, ssh_allowed=True)

    audit = db.query(AuditLog).one()
    assert result["ok"] is True
    assert captured["namespace"] == "ufw"
    assert captured["subcommand"] == "enable"
    assert captured["payload"] == {
        "confirmed": True,
        "ssh_allowed": True,
        "emergency_ssh_cidr": "203.0.113.0/24",
    }
    assert audit.action == "ufw.enable"
    assert db.get(OperationLock, node.id) is None


def test_apply_snell_config_sends_redacted_audit_payload(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    captured = {}

    def fake_run(node_payload, namespace, subcommand, payload):
        captured["namespace"] = namespace
        captured["subcommand"] = subcommand
        captured["payload"] = payload
        return ok_result({"config_path": "/etc/snell/snell-server.conf"})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = apply_snell_config(db, node.id)

    audit = db.query(AuditLog).one()
    assert result["ok"] is True
    assert captured["namespace"] == "snell"
    assert captured["subcommand"] == "config-apply"
    assert captured["payload"]["config_text"] == node.desired_config_text
    assert audit.request_json["config_text"] == "********"
    assert audit.request_json["psk"] == "********"


def test_refresh_access_candidates_upserts_candidates(monkeypatch) -> None:
    db = session()
    node = create_node(db)

    def fake_run(node_payload, namespace, subcommand, payload):
        assert namespace == "ufw"
        assert subcommand == "candidates"
        return ok_result(
            {
                "candidates": [
                    {"ip": "198.51.100.8", "port": 23456, "protocol": "tcp", "source": "ufw"},
                    {"ip": "198.51.100.8", "port": 23456, "protocol": "tcp", "source": "ufw"},
                ]
            }
        )

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = refresh_access_candidates(db, node.id)

    assert result["ok"] is True
    assert result["promoted_count"] == 0
    assert len(node.candidates) == 1
    assert node.candidates[0].hit_count == 2


def test_install_snell_sends_install_payload_and_audits(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    captured = {}

    def fake_run(node_payload, namespace, subcommand, payload):
        captured.update(namespace=namespace, subcommand=subcommand, payload=payload)
        return ok_result({"installed": True})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    result = install_snell(db, node.id, custom_binary_path="/tmp/snell-server")

    audit = db.query(AuditLog).one()
    assert result["ok"] is True
    assert captured["namespace"] == "snell"
    assert captured["subcommand"] == "install"
    assert captured["payload"]["snell_version"] == "v5.x"
    assert captured["payload"]["custom_binary_path"] == "/tmp/snell-server"
    assert captured["payload"]["config_text"] == node.desired_config_text
    assert audit.action == "snell.install"
    assert audit.request_json["config_text"] == "********"


def test_service_actions_use_fixed_subcommands(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    calls = []

    def fake_run(node_payload, namespace, subcommand, payload):
        calls.append((namespace, subcommand, payload))
        return ok_result({"commands": [["systemctl", subcommand, "snell"]]})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    for action in ["start", "stop", "restart"]:
        assert run_snell_service_action(db, node.id, action)["ok"] is True

    assert calls == [
        ("snell", "start", {"service_name": "snell"}),
        ("snell", "stop", {"service_name": "snell"}),
        ("snell", "restart", {"service_name": "snell"}),
    ]


def test_service_action_rejects_unknown_action() -> None:
    db = session()
    node = create_node(db)

    try:
        run_snell_service_action(db, node.id, "shell")
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_get_snell_config_and_logs_and_restore(monkeypatch) -> None:
    db = session()
    node = create_node(db)
    calls = []

    def fake_run(node_payload, namespace, subcommand, payload):
        calls.append((namespace, subcommand, payload))
        if subcommand == "config-get":
            return ok_result({"config_text": "listen = ::0:23456\npsk = secret\n"})
        if subcommand == "logs":
            return ok_result({"logs": "line 1\n"})
        return ok_result({"restored": True})

    monkeypatch.setattr(remote_actions, "run_remote_command", fake_run)

    assert get_snell_config(db, node.id)["data"]["config_text"].startswith("listen")
    assert read_snell_logs(db, node.id, lines=50)["data"]["logs"] == "line 1\n"
    assert restore_snell_config(db, node.id, "/backup/snell.conf.bak")["ok"] is True

    assert calls == [
        ("snell", "config-get", {}),
        ("snell", "logs", {"lines": 50}),
        ("snell", "restore", {"backup_path": "/backup/snell.conf.bak"}),
    ]
    assert [item.action for item in db.query(AuditLog).order_by(AuditLog.id)] == [
        "snell.config_get",
        "snell.logs",
        "snell.restore",
    ]
