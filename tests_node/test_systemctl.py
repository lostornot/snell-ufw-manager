from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYSTEMCTL = ROOT / "node" / "systemctl"


def run_systemctl(*args: str, stdin: str = "{}") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SYSTEMCTL), *args],
        input=stdin,
        text=True,
        capture_output=True,
    )


def parse_json(process: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(process.stdout)


def test_system_check_reports_node_tool_readiness() -> None:
    process = run_systemctl("check")

    assert process.returncode == 0
    body = parse_json(process)
    assert body["ok"] is True
    assert body["error"] is None
    data = body["data"]
    assert data["namespace"] == "system"
    assert data["subcommand"] == "check"
    assert data["running_user"]
    assert isinstance(data["effective_uid"], int)
    assert data["snell_fwctl"]["present"] is True
    assert data["snellctl"]["present"] is True
    assert data["ufwctl"]["present"] is True
    assert "present" in data["snell_binary"]
    assert "present" in data["ufw_binary"]
    assert "active" in data["ufw"]


def test_systemctl_rejects_unknown_subcommand() -> None:
    process = run_systemctl("shell")

    assert process.returncode == 2
    body = parse_json(process)
    assert body["ok"] is False
    assert body["error"]["code"] == "UNKNOWN_SUBCOMMAND"
