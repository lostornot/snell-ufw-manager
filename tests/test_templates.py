from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import create_app
from app.models import Node


def authenticated_client(monkeypatch, tmp_path=None) -> TestClient:
    if tmp_path is not None:
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'controller.db'}")
    client = TestClient(create_app())
    return client


def test_dashboard_renders_local_only_product_name(monkeypatch) -> None:
    client = authenticated_client(monkeypatch)

    response = client.get("/")

    assert response.status_code == 200
    assert "snell-ufw-manager-by-gpt" in response.text
    assert "127.0.0.1:8898" in response.text


def test_core_skeleton_pages_render(monkeypatch) -> None:
    client = authenticated_client(monkeypatch)

    for path, label in [
        ("/nodes", "节点"),
        ("/relay-groups", "中转组"),
        ("/policies", "访问策略"),
        ("/audit-logs", "操作日志"),
    ]:
        response = client.get(path)
        assert response.status_code == 200
        assert label in response.text


def test_dashboard_summarizes_node_connectivity(monkeypatch, tmp_path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    with SessionLocal() as db:
        db.add_all(
            [
                Node(
                    name="Online",
                    host="203.0.113.10",
                    ssh_port=22,
                    ssh_user="snellmgr",
                    snell_port=23456,
                    last_seen_at=datetime(2026, 6, 27, 10, 0, tzinfo=timezone.utc),
                ),
                Node(
                    name="Offline",
                    host="203.0.113.11",
                    ssh_port=22,
                    ssh_user="snellmgr",
                    snell_port=23456,
                    last_error="connection refused",
                ),
                Node(
                    name="Unchecked",
                    host="203.0.113.12",
                    ssh_port=22,
                    ssh_user="snellmgr",
                    snell_port=23456,
                ),
            ]
        )
        db.commit()

    response = client.get("/")

    assert "在线" in response.text
    assert "离线" in response.text
    assert "未检查" in response.text
    assert "Online" in response.text
    assert "Offline" in response.text
    assert "Unchecked" in response.text
