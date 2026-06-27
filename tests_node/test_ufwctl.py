from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UFWCTL = ROOT / "node" / "ufwctl"


def run_ufwctl(subcommand: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(UFWCTL), subcommand],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )


def body(process: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(process.stdout)


def test_list_reports_inactive_warning() -> None:
    process = run_ufwctl(
        "list",
        {
            "dry_run": True,
            "ufw_status": "inactive",
            "default_incoming": "deny",
            "ssh_allowed": True,
            "managed_rules": [],
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["active"] is False
    assert "UFW inactive" in data["warnings"][0]


def test_apply_deletes_matching_managed_rules_in_reverse_order() -> None:
    process = run_ufwctl(
        "apply",
        {
            "dry_run": True,
            "ufw_status": "active",
            "node_id": 10,
            "port": 23456,
            "rules": [
                {
                    "group_id": 3,
                    "source": "198.51.100.8",
                    "proto": "tcp",
                    "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
                }
            ],
            "existing_rules": [
                {
                    "number": 1,
                    "action": "allow",
                    "port": 22,
                    "proto": "tcp",
                    "comment": "ssh",
                },
                {
                    "number": 2,
                    "action": "allow",
                    "port": 23456,
                    "proto": "tcp",
                    "comment": "manual snell",
                },
                {
                    "number": 3,
                    "action": "allow",
                    "port": 23456,
                    "proto": "tcp",
                    "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
                },
                {
                    "number": 5,
                    "action": "allow",
                    "port": 23456,
                    "proto": "tcp",
                    "comment": "snell-control:node:10:group:4:port:23456:proto:tcp",
                },
            ],
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["delete_numbers"] == [5, 3]
    assert data["preserved_numbers"] == [1, 2]
    assert data["would_enable"] is False


def test_apply_inactive_does_not_reload_or_enable() -> None:
    process = run_ufwctl(
        "apply",
        {
            "dry_run": True,
            "ufw_status": "inactive",
            "node_id": 10,
            "port": 23456,
            "rules": [],
            "existing_rules": [],
        },
    )

    data = body(process)["data"]
    assert data["would_reload"] is False
    assert data["would_enable"] is False
    assert data["warnings"]


def test_enable_refuses_without_safe_ssh_allow() -> None:
    process = run_ufwctl(
        "enable",
        {
            "dry_run": True,
            "ssh_allowed": False,
            "emergency_ssh_cidr": None,
            "confirmed": True,
        },
    )

    assert process.returncode == 2
    response = body(process)
    assert response["ok"] is False
    assert response["error"]["code"] == "UFW_ENABLE_UNSAFE"


def test_enable_refuses_without_confirmation() -> None:
    process = run_ufwctl(
        "enable",
        {
            "dry_run": True,
            "ssh_allowed": True,
            "emergency_ssh_cidr": "203.0.113.0/24",
            "confirmed": False,
        },
    )

    assert process.returncode == 2
    assert body(process)["error"]["code"] == "UFW_ENABLE_UNCONFIRMED"


def test_enable_returns_command_plan_for_safe_dry_run() -> None:
    process = run_ufwctl(
        "enable",
        {
            "dry_run": True,
            "ssh_allowed": True,
            "emergency_ssh_cidr": "203.0.113.0/24",
            "confirmed": True,
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["commands"] == [["ufw", "--force", "enable"]]
    assert data["would_enable"] is True
    assert data["enabled"] is False


def test_list_parses_ufw_status_numbered_fixture() -> None:
    process = run_ufwctl(
        "list",
        {
            "dry_run": True,
            "ufw_status_output": "\n".join(
                [
                    "Status: active",
                    "Default: deny (incoming), allow (outgoing), disabled (routed)",
                    "",
                    "[ 1] 22/tcp ALLOW IN Anywhere # ssh",
                    "[ 2] 23456/tcp ALLOW IN 198.51.100.8 # snell-control:node:10:group:3:port:23456:proto:tcp",
                    "[ 3] 23456/udp ALLOW IN 198.51.100.8 # snell-control:node:10:group:3:port:23456:proto:udp",
                ]
            ),
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["active"] is True
    assert data["default_incoming"] == "deny"
    assert data["ssh_allowed"] is True
    assert data["managed_rules"] == [
        {
            "number": 2,
            "action": "allow",
            "port": 23456,
            "proto": "tcp",
            "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
            "from": "198.51.100.8",
        },
        {
            "number": 3,
            "action": "allow",
            "port": 23456,
            "proto": "udp",
            "comment": "snell-control:node:10:group:3:port:23456:proto:udp",
            "from": "198.51.100.8",
        },
    ]


def test_apply_returns_exact_ufw_command_plan_for_dry_run() -> None:
    process = run_ufwctl(
        "apply",
        {
            "dry_run": True,
            "ufw_status": "active",
            "node_id": 10,
            "port": 23456,
            "rules": [
                {
                    "group_id": 3,
                    "source": "198.51.100.8",
                    "proto": "tcp",
                    "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
                }
            ],
            "existing_rules": [
                {
                    "number": 3,
                    "action": "allow",
                    "port": 23456,
                    "proto": "tcp",
                    "comment": "snell-control:node:10:group:3:port:23456:proto:tcp",
                }
            ],
        },
    )

    data = body(process)["data"]
    assert data["commands"] == [
        ["ufw", "--force", "delete", "3"],
        [
            "ufw",
            "allow",
            "proto",
            "tcp",
            "from",
            "198.51.100.8",
            "to",
            "any",
            "port",
            "23456",
            "comment",
            "snell-control:node:10:group:3:port:23456:proto:tcp",
        ],
        ["ufw", "reload"],
    ]


def test_backup_copies_user_rules_files(tmp_path: Path) -> None:
    user_rules = tmp_path / "user.rules"
    user6_rules = tmp_path / "user6.rules"
    backup_dir = tmp_path / "backups"
    user_rules.write_text("*filter\n")
    user6_rules.write_text("*filter6\n")

    process = run_ufwctl(
        "backup",
        {
            "user_rules_path": str(user_rules),
            "user6_rules_path": str(user6_rules),
            "backup_dir": str(backup_dir),
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert Path(data["user_rules_backup"]).read_text() == "*filter\n"
    assert Path(data["user6_rules_backup"]).read_text() == "*filter6\n"


def test_candidates_parse_log_lines_for_port_and_protocol() -> None:
    process = run_ufwctl(
        "candidates",
        {
            "port": 23456,
            "log_text": "\n".join(
                [
                    "Jun 26 kernel: [UFW BLOCK] SRC=198.51.100.8 DST=203.0.113.10 PROTO=TCP SPT=51000 DPT=23456",
                    "Jun 26 kernel: [UFW BLOCK] SRC=198.51.100.9 DST=203.0.113.10 PROTO=UDP SPT=51000 DPT=23456",
                    "Jun 26 kernel: [UFW BLOCK] SRC=198.51.100.10 DST=203.0.113.10 PROTO=TCP SPT=51000 DPT=22",
                ]
            ),
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["candidates"] == [
        {"ip": "198.51.100.8", "port": 23456, "protocol": "tcp", "source": "ufw", "hit_count": 1},
        {"ip": "198.51.100.9", "port": 23456, "protocol": "udp", "source": "ufw", "hit_count": 1},
    ]
