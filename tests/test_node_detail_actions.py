from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import create_app
from app.models import AccessCandidate, AuditLog, RelayGroup


def csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def setup_node(client: TestClient) -> None:
    token = csrf_token(client.get("/nodes").text)
    client.post(
        "/nodes",
        data={
            "csrf_token": token,
            "name": "Tokyo 1",
            "host": "203.0.113.10",
            "ssh_port": "22",
            "ssh_user": "snellmgr",
            "snell_port": "23456",
            "snell_version": "v5.x",
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
        },
    )


def authenticated_client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'controller.db'}")
    client = TestClient(create_app())
    setup_node(client)
    return client


def test_node_detail_page_renders_action_forms(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)

    response = client.get("/nodes/1")

    assert response.status_code == 200
    assert "Tokyo 1" in response.text
    assert 'action="/nodes/1/refresh-status"' in response.text
    assert 'action="/nodes/1/install-snell"' in response.text
    assert 'action="/nodes/1/snell-start"' in response.text
    assert 'action="/nodes/1/snell-stop"' in response.text
    assert 'action="/nodes/1/snell-restart"' in response.text
    assert 'action="/nodes/1/snell-config-get"' in response.text
    assert 'action="/nodes/1/snell-logs"' in response.text
    assert 'action="/nodes/1/snell-restore"' in response.text
    assert 'action="/nodes/1/ufw-list"' in response.text
    assert 'action="/nodes/1/apply-ufw"' in response.text
    assert 'action="/nodes/1/enable-ufw"' in response.text
    assert 'action="/nodes/1/apply-config"' in response.text
    assert 'action="/nodes/1/candidates"' in response.text
    assert 'action="/nodes/1/check-environment"' in response.text
    assert 'action="/nodes/1/edit"' in response.text
    assert 'action="/nodes/1/config"' in response.text
    assert 'action="/nodes/1/delete"' in response.text
    nodes_page = client.get("/nodes")
    assert "添加已有节点" in nodes_page.text
    assert "新 VPS 接入" in nodes_page.text
    assert 'action="/nodes/1/check-environment"' in nodes_page.text


def test_node_detail_actions_call_remote_services(monkeypatch, tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_action(db, node_id, **kwargs):
        calls.append(str(node_id))
        return {"ok": True, "data": {}, "error": None}

    import app.main as main_module

    monkeypatch.setattr(main_module, "refresh_node_status", fake_action)
    monkeypatch.setattr(main_module, "install_snell", fake_action)
    monkeypatch.setattr(main_module, "refresh_ufw_list", fake_action)
    monkeypatch.setattr(main_module, "apply_ufw_policy", fake_action)
    monkeypatch.setattr(main_module, "enable_ufw", fake_action)
    monkeypatch.setattr(main_module, "apply_snell_config", fake_action)
    monkeypatch.setattr(main_module, "refresh_access_candidates", fake_action)
    monkeypatch.setattr(main_module, "check_node_environment", fake_action)

    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/nodes/1").text)

    for path in [
        "/nodes/1/refresh-status",
        "/nodes/1/install-snell",
        "/nodes/1/ufw-list",
        "/nodes/1/apply-ufw",
        "/nodes/1/enable-ufw",
        "/nodes/1/apply-config",
        "/nodes/1/candidates",
        "/nodes/1/check-environment",
    ]:
        response = client.post(path, data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/nodes/1"

    assert calls == ["1", "1", "1", "1", "1", "1", "1", "1"]


def test_node_detail_snell_service_actions_call_remote_services(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str]] = []

    def fake_service_action(db, node_id, action):
        calls.append((str(node_id), action))
        return {"ok": True, "data": {}, "error": None}

    import app.main as main_module

    monkeypatch.setattr(main_module, "run_snell_service_action", fake_service_action)

    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/nodes/1").text)

    for path in ["/nodes/1/snell-start", "/nodes/1/snell-stop", "/nodes/1/snell-restart"]:
        response = client.post(path, data={"csrf_token": token}, follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/nodes/1"

    assert calls == [("1", "start"), ("1", "stop"), ("1", "restart")]


def test_node_detail_config_logs_restore_actions_call_remote_services(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, str | int | None]] = []

    def fake_config_get(db, node_id):
        calls.append(("config-get", str(node_id)))
        return {"ok": True, "data": {}, "error": None}

    def fake_logs(db, node_id, *, lines=100):
        calls.append(("logs", lines))
        return {"ok": True, "data": {}, "error": None}

    def fake_restore(db, node_id, backup_path):
        calls.append(("restore", backup_path))
        return {"ok": True, "data": {}, "error": None}

    import app.main as main_module

    monkeypatch.setattr(main_module, "get_snell_config", fake_config_get)
    monkeypatch.setattr(main_module, "read_snell_logs", fake_logs)
    monkeypatch.setattr(main_module, "restore_snell_config", fake_restore)

    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/nodes/1").text)

    assert client.post("/nodes/1/snell-config-get", data={"csrf_token": token}, follow_redirects=False).status_code == 303
    assert client.post("/nodes/1/snell-logs", data={"csrf_token": token, "lines": "50"}, follow_redirects=False).status_code == 303
    assert client.post(
        "/nodes/1/snell-restore",
        data={"csrf_token": token, "backup_path": "/backup/snell.conf.bak"},
        follow_redirects=False,
    ).status_code == 303

    assert calls == [("config-get", "1"), ("logs", 50), ("restore", "/backup/snell.conf.bak")]


def test_node_detail_promotes_access_candidate_to_relay_group(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    with SessionLocal() as db:
        group = RelayGroup(name="relay-a")
        candidate = AccessCandidate(
            node_id=1,
            ip="198.51.100.8",
            port=23456,
            protocol="udp",
            hit_count=3,
            source="ufw",
        )
        db.add_all([group, candidate])
        db.commit()

    detail = client.get("/nodes/1")
    assert 'action="/nodes/1/candidates/1/promote"' in detail.text
    assert "relay-a" in detail.text
    token = csrf_token(detail.text)
    response = client.post(
        "/nodes/1/candidates/1/promote",
        data={"csrf_token": token, "relay_group_id": "1", "confirmed": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    relay_page = client.get("/relay-groups")
    assert "198.51.100.8" in relay_page.text
    detail = client.get("/nodes/1")
    assert "promoted" in detail.text


def test_node_detail_shows_latest_remote_ufw_whitelist(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    with SessionLocal() as db:
        audit = AuditLog(
            actor="admin",
            action="ufw.list",
            target_type="node",
            target_id=1,
            summary="listed UFW rules on Tokyo 1",
            success=True,
            result_json={
                "ok": True,
                "data": {
                    "active": False,
                    "default_incoming": "deny",
                    "managed_rules": [
                        {
                            "source": "198.51.100.8",
                            "proto": "udp",
                            "port": 23456,
                            "comment": "snell-control:node:1:group:1:port:23456:proto:udp",
                        }
                    ],
                },
            },
        )
        db.add(audit)
        db.commit()

    detail = client.get("/nodes/1")

    assert "当前 Snell UFW 白名单" in detail.text
    assert "UFW 未启用" in detail.text
    assert "198.51.100.8" in detail.text
    assert "snell-control:node:1:group:1:port:23456:proto:udp" in detail.text


def test_node_detail_shows_bootstrap_steps_and_latest_check(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    with SessionLocal() as db:
        audit = AuditLog(
            actor="admin",
            action="node.check",
            target_type="node",
            target_id=1,
            summary="node.check for Tokyo 1",
            success=True,
            result_json={
                "ok": True,
                "data": {
                    "snell_fwctl": {"present": True},
                    "snellctl": {"present": True},
                    "ufwctl": {"present": True},
                    "snell_binary": {"present": False},
                    "ufw_binary": {"present": True},
                    "ufw": {"active": False},
                },
            },
        )
        db.add(audit)
        db.commit()

    detail = client.get("/nodes/1")

    assert "节点初始化" in detail.text
    assert "scripts/install-node.sh" in detail.text
    assert "snell-ufw-manager-by-gpt" in detail.text
    assert "snellmgr" in detail.text
    assert 'action="/nodes/1/check-environment"' in detail.text
    assert "snell-fwctl" in detail.text
    assert "未安装" in detail.text
