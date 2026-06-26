from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "node" / "snell-fwctl"


def run_fwctl(*args: str, stdin: str = "{}") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(ENTRYPOINT), *args],
        input=stdin,
        text=True,
        capture_output=True,
    )


def parse_json(process: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(process.stdout)


def test_rejects_unknown_namespace() -> None:
    process = run_fwctl("shell", "status")

    assert process.returncode == 2
    body = parse_json(process)
    assert body["ok"] is False
    assert body["error"]["code"] == "UNKNOWN_NAMESPACE"


def test_rejects_unknown_subcommand() -> None:
    process = run_fwctl("snell", "shell")

    assert process.returncode == 2
    body = parse_json(process)
    assert body["ok"] is False
    assert body["error"]["code"] == "UNKNOWN_SUBCOMMAND"


def test_rejects_extra_arguments() -> None:
    process = run_fwctl("snell", "status", "extra")

    assert process.returncode == 2
    body = parse_json(process)
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_ARGUMENTS"


def test_rejects_invalid_json() -> None:
    process = run_fwctl("snell", "status", stdin="{bad json")

    assert process.returncode == 2
    body = parse_json(process)
    assert body["ok"] is False
    assert body["error"]["code"] == "INVALID_JSON"


def test_dispatches_snell_status() -> None:
    process = run_fwctl("snell", "status")

    assert process.returncode == 0
    body = parse_json(process)
    assert body["ok"] is True
    assert body["error"] is None
    assert body["data"]["namespace"] == "snell"
    assert body["data"]["subcommand"] == "status"
    assert body["data"]["status"] == "unknown"


def test_dispatches_ufw_list() -> None:
    process = run_fwctl("ufw", "list", stdin='{"port":23456}')

    assert process.returncode == 0
    body = parse_json(process)
    assert body["ok"] is True
    assert body["data"]["namespace"] == "ufw"
    assert body["data"]["subcommand"] == "list"
    assert body["data"]["active"] is False
    assert body["data"]["warnings"]


def test_dispatches_system_check() -> None:
    process = run_fwctl("system", "check")

    assert process.returncode == 0
    body = parse_json(process)
    assert body["ok"] is True
    assert body["error"] is None
    assert body["data"]["namespace"] == "system"
    assert body["data"]["subcommand"] == "check"
    assert body["data"]["snell_fwctl"]["present"] is True
