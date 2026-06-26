from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_tool(tool: str, subcommand: str, stdin: str = "{}") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ROOT / "node" / tool), subcommand],
        input=stdin,
        text=True,
        capture_output=True,
    )


def assert_json_contract(process: subprocess.CompletedProcess[str]) -> dict:
    body = json.loads(process.stdout)
    assert set(body.keys()) == {"ok", "data", "error"}
    return body


def test_snellctl_status_uses_normalized_success_contract() -> None:
    process = run_tool("snellctl", "status")

    assert process.returncode == 0
    body = assert_json_contract(process)
    assert body["ok"] is True
    assert body["error"] is None
    assert body["data"]["namespace"] == "snell"


def test_ufwctl_list_uses_normalized_success_contract() -> None:
    process = run_tool("ufwctl", "list")

    assert process.returncode == 0
    body = assert_json_contract(process)
    assert body["ok"] is True
    assert body["error"] is None
    assert body["data"]["namespace"] == "ufw"


def test_internal_tools_reject_unknown_subcommands() -> None:
    for tool in ["snellctl", "ufwctl"]:
        process = run_tool(tool, "unknown")
        body = assert_json_contract(process)

        assert process.returncode == 2
        assert body["ok"] is False
        assert body["error"]["code"] == "UNKNOWN_SUBCOMMAND"

