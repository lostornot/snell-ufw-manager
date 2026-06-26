from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def authenticated_client(monkeypatch) -> TestClient:
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
