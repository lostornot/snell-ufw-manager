from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import create_app


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_unauthenticated_dashboard_redirects_to_login() -> None:
    client = TestClient(create_app())

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_valid_admin_token_creates_session_cookie(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app())

    response = client.post(
        "/login",
        data={"admin_token": "test-admin-token"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "snell_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]


def test_invalid_admin_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app())

    response = client.post("/login", data={"admin_token": "wrong"})

    assert response.status_code == 401
    assert "Invalid admin token" in response.text


def test_post_without_csrf_is_rejected(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app())
    client.post("/login", data={"admin_token": "test-admin-token"})

    response = client.post("/nodes/stub")

    assert response.status_code == 403


def test_post_with_csrf_reaches_stub_handler(monkeypatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "test-admin-token")
    client = TestClient(create_app())
    client.post("/login", data={"admin_token": "test-admin-token"})
    dashboard = client.get("/")
    csrf_token = extract_csrf(dashboard.text)

    response = client.post("/nodes/stub", data={"csrf_token": csrf_token})

    assert response.status_code == 200
    assert response.text == "stub ok"

