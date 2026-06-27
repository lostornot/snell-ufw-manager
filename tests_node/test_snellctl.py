from __future__ import annotations

import json
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNELLCTL = ROOT / "node" / "snellctl"


def run_snellctl(subcommand: str, payload: dict) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SNELLCTL), subcommand],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
    )


def body(process: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(process.stdout)


def test_install_refuses_implicit_latest_version() -> None:
    process = run_snellctl(
        "install",
        {"dry_run": True, "snell_version": "latest", "config_text": "psk = secret\n"},
    )

    assert process.returncode == 2
    response = body(process)
    assert response["ok"] is False
    assert response["error"]["code"] == "SNELL_VERSION_NOT_PINNED"


def test_install_accepts_explicit_version() -> None:
    process = run_snellctl(
        "install",
        {
            "dry_run": True,
            "snell_version": "v5.x",
            "snell_arch": "amd64",
            "config_text": "listen = ::0:23456\npsk = secret\n",
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["version"] == "v5.x"
    assert data["would_install"] is True


def test_config_apply_backs_up_existing_config_before_write(tmp_path: Path) -> None:
    config_path = tmp_path / "snell-server.conf"
    backup_dir = tmp_path / "backup"
    config_path.write_text("listen = ::0:10000\npsk = old\n")

    process = run_snellctl(
        "config-apply",
        {
            "dry_run": True,
            "config_path": str(config_path),
            "backup_dir": str(backup_dir),
            "config_text": "listen = ::0:23456\npsk = new\n",
            "restart_success": True,
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["backup_path"]
    assert Path(data["backup_path"]).read_text() == "listen = ::0:10000\npsk = old\n"
    assert config_path.read_text() == "listen = ::0:23456\npsk = new\n"


def test_config_apply_rolls_back_when_restart_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "snell-server.conf"
    backup_dir = tmp_path / "backup"
    old_config = "listen = ::0:10000\npsk = old\n"
    config_path.write_text(old_config)

    process = run_snellctl(
        "config-apply",
        {
            "dry_run": True,
            "config_path": str(config_path),
            "backup_dir": str(backup_dir),
            "config_text": "listen = ::0:23456\npsk = broken\n",
            "restart_success": False,
        },
    )

    assert process.returncode == 2
    response = body(process)
    assert response["ok"] is False
    assert response["error"]["code"] == "SNELL_RESTART_FAILED"
    assert config_path.read_text() == old_config


def test_status_normalizes_systemd_active_state() -> None:
    process = run_snellctl(
        "status",
        {"dry_run": True, "systemctl_active": "active", "version": "v5.x", "port": 23456},
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert data["status"] == "running"
    assert data["version"] == "v5.x"
    assert data["port"] == 23456


def test_install_from_custom_binary_writes_binary_config_and_service(tmp_path: Path) -> None:
    source_binary = tmp_path / "snell-server-src"
    install_path = tmp_path / "bin" / "snell-server"
    config_path = tmp_path / "etc" / "snell-server.conf"
    service_path = tmp_path / "systemd" / "snell.service"
    backup_dir = tmp_path / "backup"
    source_binary.write_bytes(b"fake snell binary")
    digest = hashlib.sha256(b"fake snell binary").hexdigest()

    process = run_snellctl(
        "install",
        {
            "snell_version": "v5.x",
            "custom_binary_path": str(source_binary),
            "snell_sha256": digest,
            "install_path": str(install_path),
            "config_path": str(config_path),
            "service_path": str(service_path),
            "backup_dir": str(backup_dir),
            "config_text": "listen = ::0:23456\npsk = secret\n",
            "restart_success": True,
            "skip_systemctl": True,
        },
    )

    assert process.returncode == 0
    data = body(process)["data"]
    assert install_path.read_bytes() == b"fake snell binary"
    assert config_path.read_text() == "listen = ::0:23456\npsk = secret\n"
    assert "ExecStart=" + str(install_path) in service_path.read_text()
    assert data["installed"] is True
    assert data["commands"] == [
        ["install", "-m", "0755", str(source_binary), str(install_path)],
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "snell"],
        ["systemctl", "restart", "snell"],
        ["systemctl", "is-active", "snell"],
    ]


def test_install_refuses_custom_binary_with_wrong_sha256(tmp_path: Path) -> None:
    source_binary = tmp_path / "snell-server-src"
    install_path = tmp_path / "bin" / "snell-server"
    source_binary.write_bytes(b"fake snell binary")

    process = run_snellctl(
        "install",
        {
            "snell_version": "v5.x",
            "custom_binary_path": str(source_binary),
            "snell_sha256": "0" * 64,
            "install_path": str(install_path),
            "config_path": str(tmp_path / "snell.conf"),
            "service_path": str(tmp_path / "snell.service"),
            "config_text": "psk = secret\n",
            "skip_systemctl": True,
        },
    )

    assert process.returncode == 2
    assert body(process)["error"]["code"] == "SNELL_CHECKSUM_MISMATCH"
    assert not install_path.exists()


def test_install_non_dry_run_requires_binary_source(tmp_path: Path) -> None:
    process = run_snellctl(
        "install",
        {
            "snell_version": "v5.x",
            "install_path": str(tmp_path / "snell-server"),
            "config_path": str(tmp_path / "snell.conf"),
            "service_path": str(tmp_path / "snell.service"),
            "config_text": "psk = secret\n",
        },
    )

    assert process.returncode == 2
    assert body(process)["error"]["code"] == "SNELL_BINARY_SOURCE_REQUIRED"


def test_dry_run_install_returns_command_plan_without_writing(tmp_path: Path) -> None:
    install_path = tmp_path / "snell-server"
    process = run_snellctl(
        "install",
        {
            "dry_run": True,
            "snell_version": "v5.x",
            "custom_binary_path": str(tmp_path / "source"),
            "install_path": str(install_path),
            "config_path": str(tmp_path / "snell.conf"),
            "service_path": str(tmp_path / "snell.service"),
            "config_text": "psk = secret\n",
        },
    )

    data = body(process)["data"]
    assert data["would_install"] is True
    assert data["commands"][0] == ["install", "-m", "0755", str(tmp_path / "source"), str(install_path)]
    assert not install_path.exists()


def test_service_commands_return_systemctl_plan_in_dry_run() -> None:
    for subcommand in ["start", "stop", "restart"]:
        process = run_snellctl(subcommand, {"dry_run": True, "service_name": "snell"})
        assert process.returncode == 0
        data = body(process)["data"]
        assert data["commands"] == [["systemctl", subcommand, "snell"]]


def test_config_get_reads_config_file(tmp_path: Path) -> None:
    config_path = tmp_path / "snell-server.conf"
    config_path.write_text("listen = ::0:23456\npsk = secret\n")

    process = run_snellctl("config-get", {"config_path": str(config_path)})

    assert process.returncode == 0
    assert body(process)["data"]["config_text"] == "listen = ::0:23456\npsk = secret\n"


def test_restore_copies_backup_to_config_path(tmp_path: Path) -> None:
    backup_path = tmp_path / "snell-server.conf.bak"
    config_path = tmp_path / "snell-server.conf"
    backup_path.write_text("listen = ::0:10000\npsk = old\n")
    config_path.write_text("listen = ::0:23456\npsk = bad\n")

    process = run_snellctl(
        "restore",
        {
            "backup_path": str(backup_path),
            "config_path": str(config_path),
            "skip_systemctl": True,
        },
    )

    assert process.returncode == 0
    assert config_path.read_text() == "listen = ::0:10000\npsk = old\n"


def test_logs_returns_log_text_or_journalctl_plan() -> None:
    process = run_snellctl("logs", {"log_text": "line 1\nline 2\n"})

    assert process.returncode == 0
    assert body(process)["data"]["logs"] == "line 1\nline 2\n"

    process = run_snellctl("logs", {"dry_run": True, "service_name": "snell", "lines": 50})
    assert body(process)["data"]["commands"] == [["journalctl", "-u", "snell", "--no-pager", "-n", "50"]]
