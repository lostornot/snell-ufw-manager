from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import create_app


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match is not None
    return match.group(1)


def test_dashboard_creates_local_session_without_admin_token() -> None:
    client = TestClient(create_app())

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "snell_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert "节点状态" in response.text


def test_login_page_is_removed() -> None:
    client = TestClient(create_app())

    response = client.get("/login")

    assert response.status_code in {404, 405}


def test_post_without_csrf_is_rejected() -> None:
    client = TestClient(create_app())
    client.get("/")

    response = client.post("/relay-groups", data={"name": "relay-a"})

    assert response.status_code == 403


def test_post_with_csrf_reaches_real_state_changing_handler() -> None:
    client = TestClient(create_app())
    page = client.get("/relay-groups")
    csrf_token = extract_csrf(page.text)

    response = client.post(
        "/relay-groups",
        data={"csrf_token": csrf_token, "name": "relay-a"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/relay-groups"
    assert "relay-a" in client.get("/relay-groups").text


def test_test_only_stub_route_is_not_exposed() -> None:
    client = TestClient(create_app())
    client.get("/")

    response = client.post("/nodes/stub")

    assert response.status_code in {404, 405}
