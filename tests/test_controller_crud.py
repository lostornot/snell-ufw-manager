from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app


def csrf_token(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def authenticated_client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'controller.db'}")
    client = TestClient(create_app())
    return client


def test_create_node_from_form_and_list_it(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/nodes").text)

    response = client.post(
        "/nodes",
        data={
            "csrf_token": token,
            "name": "Tokyo 1",
            "host": "203.0.113.10",
            "ssh_alias": "",
            "ssh_port": "22",
            "ssh_user": "snellmgr",
            "snell_port": "23456",
            "snell_version": "v5.x",
            "psk": "shared-secret",
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
            "remark": "primary node",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/nodes/1"
    page = client.get("/nodes")
    assert "Tokyo 1" in page.text
    assert "203.0.113.10" in page.text
    assert "23456" in page.text


def test_invalid_node_form_returns_bad_request(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/nodes").text)

    response = client.post(
        "/nodes",
        data={
            "csrf_token": token,
            "name": "No Host",
            "host": "",
            "ssh_alias": "",
            "ssh_port": "22",
            "ssh_user": "snellmgr",
            "snell_port": "23456",
            "enable_tcp": "on",
        },
        follow_redirects=False,
    )

    assert response.status_code == 400
    assert "host is required" in response.text


def test_edit_node_from_detail_page(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
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
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
        },
    )

    detail = client.get("/nodes/1")
    assert 'action="/nodes/1/edit"' in detail.text
    token = csrf_token(detail.text)
    response = client.post(
        "/nodes/1/edit",
        data={
            "csrf_token": token,
            "name": "Tokyo updated",
            "host": "203.0.113.11",
            "ssh_alias": "",
            "ssh_port": "2222",
            "ssh_user": "snellmgr",
            "snell_port": "23457",
            "snell_version": "v5.0.1",
            "psk": "new-secret",
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
            "remark": "updated remark",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/nodes/1")
    assert "Tokyo updated" in page.text
    assert "203.0.113.11" in page.text
    assert "23457" in page.text


def test_delete_node_from_detail_page(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
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
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
        },
    )

    detail = client.get("/nodes/1")
    assert 'action="/nodes/1/delete"' in detail.text
    token = csrf_token(detail.text)
    response = client.post("/nodes/1/delete", data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 303
    page = client.get("/nodes")
    assert "Tokyo 1" not in page.text


def test_update_node_desired_config(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
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
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
        },
    )

    detail = client.get("/nodes/1")
    assert 'action="/nodes/1/config"' in detail.text
    token = csrf_token(detail.text)
    response = client.post(
        "/nodes/1/config",
        data={
            "csrf_token": token,
            "desired_config_text": "listen = ::0:23456\npsk = panel-secret\n",
            "psk": "panel-secret",
            "snell_version": "v5.0.1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/nodes/1")
    assert "listen = ::0:23456" in page.text
    assert "v5.0.1" in page.text


def test_create_profile_from_form(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/profiles").text)

    response = client.post(
        "/profiles",
        data={
            "csrf_token": token,
            "name": "default-v5",
            "snell_port": "23456",
            "snell_version": "v5.x",
            "psk": "shared-secret",
            "enable_tcp": "on",
            "enable_udp": "on",
            "config_text": "listen = ::0:23456\npsk = shared-secret\n",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/profiles")
    assert "default-v5" in page.text
    assert "v5.x" in page.text


def test_create_relay_group_and_ip(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/relay-groups").text)

    response = client.post(
        "/relay-groups",
        data={"csrf_token": token, "name": "relay-a", "remark": "hk relay"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/relay-groups")
    assert "relay-a" in page.text
    token = csrf_token(page.text)

    response = client.post(
        "/relay-groups/1/ips",
        data={"csrf_token": token, "value": "198.51.100.0/24", "remark": "egress"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    page = client.get("/relay-groups")
    assert "198.51.100.0/24" in page.text


def test_edit_and_delete_relay_group(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups", data={"csrf_token": token, "name": "relay-a", "remark": "old"})

    page = client.get("/relay-groups")
    assert 'action="/relay-groups/1/edit"' in page.text
    assert 'action="/relay-groups/1/delete"' in page.text
    token = csrf_token(page.text)
    response = client.post(
        "/relay-groups/1/edit",
        data={"csrf_token": token, "name": "relay-b", "remark": "new"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/relay-groups")
    assert "relay-b" in page.text
    assert "relay-a" not in page.text

    token = csrf_token(page.text)
    response = client.post("/relay-groups/1/delete", data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 303
    page = client.get("/relay-groups")
    assert "relay-b" not in page.text


def test_delete_relay_ip(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups", data={"csrf_token": token, "name": "relay-a"})
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups/1/ips", data={"csrf_token": token, "value": "198.51.100.8"})

    page = client.get("/relay-groups")
    assert 'action="/relay-groups/1/ips/1/delete"' in page.text
    token = csrf_token(page.text)
    response = client.post("/relay-groups/1/ips/1/delete", data={"csrf_token": token}, follow_redirects=False)

    assert response.status_code == 303
    page = client.get("/relay-groups")
    assert "198.51.100.8" not in page.text


def test_bind_policy_and_show_preview(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
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
            "enable_tcp": "on",
            "enable_udp": "on",
            "enabled": "on",
        },
    )
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups", data={"csrf_token": token, "name": "relay-a"})
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups/1/ips", data={"csrf_token": token, "value": "198.51.100.8"})

    token = csrf_token(client.get("/policies").text)
    response = client.post(
        "/policies",
        data={"csrf_token": token, "node_id": "1", "relay_group_id": "1", "enabled": "on"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    page = client.get("/policies")
    assert "Tokyo 1" in page.text
    assert "relay-a" in page.text
    assert "198.51.100.8" in page.text
    assert "snell-control:node:1:group:1:port:23456:proto:tcp" in page.text


def test_audit_log_lists_created_actions(monkeypatch, tmp_path: Path) -> None:
    client = authenticated_client(monkeypatch, tmp_path)
    token = csrf_token(client.get("/relay-groups").text)
    client.post("/relay-groups", data={"csrf_token": token, "name": "relay-a"})

    page = client.get("/audit-logs")

    assert page.status_code == 200
    assert "relay_group.create" in page.text
    assert "relay-a" in page.text
