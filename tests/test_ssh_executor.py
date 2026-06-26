from __future__ import annotations

import subprocess

import pytest

from app.schemas import NodeCreate
from app.services.ssh_executor import (
    SSHExecutionError,
    build_ssh_command,
    run_remote_command,
)


def field_node() -> NodeCreate:
    return NodeCreate(
        name="Tokyo 1",
        host="203.0.113.10",
        ssh_port=2222,
        ssh_user="snellmgr",
        snell_port=23456,
        enable_tcp=True,
        enable_udp=True,
    )


def alias_node() -> NodeCreate:
    return NodeCreate(
        name="Tokyo 1",
        ssh_alias="tokyo-snell",
        host=None,
        ssh_port=None,
        ssh_user=None,
        snell_port=23456,
        enable_tcp=True,
        enable_udp=True,
    )


def test_builds_field_based_ssh_command_array() -> None:
    command = build_ssh_command(field_node(), "snell", "status")

    assert command == [
        "ssh",
        "-p",
        "2222",
        "snellmgr@203.0.113.10",
        "sudo",
        "/usr/local/sbin/snell-fwctl",
        "snell",
        "status",
    ]


def test_builds_alias_based_ssh_command_array() -> None:
    command = build_ssh_command(alias_node(), "ufw", "list")

    assert command == [
        "ssh",
        "tokyo-snell",
        "sudo",
        "/usr/local/sbin/snell-fwctl",
        "ufw",
        "list",
    ]


def test_builds_system_check_command_array() -> None:
    command = build_ssh_command(field_node(), "system", "check")

    assert command == [
        "ssh",
        "-p",
        "2222",
        "snellmgr@203.0.113.10",
        "sudo",
        "/usr/local/sbin/snell-fwctl",
        "system",
        "check",
    ]


def test_field_based_command_can_include_identity_file() -> None:
    node = field_node()
    node.ssh_key_path = "/Users/me/.ssh/snell_control_ed25519"

    command = build_ssh_command(node, "snell", "status")

    assert command[:4] == ["ssh", "-i", "/Users/me/.ssh/snell_control_ed25519", "-p"]


@pytest.mark.parametrize(
    ("namespace", "subcommand"),
    [
        ("bad", "status"),
        ("snell", "shell"),
        ("ufw", "start"),
    ],
)
def test_rejects_bad_namespace_or_subcommand(namespace: str, subcommand: str) -> None:
    with pytest.raises(SSHExecutionError):
        build_ssh_command(field_node(), namespace, subcommand)


def test_rejects_dash_prefixed_alias_before_subprocess() -> None:
    node = alias_node()
    node.ssh_alias = "-oProxyCommand=sh"

    with pytest.raises(SSHExecutionError):
        build_ssh_command(node, "snell", "status")


def test_rejects_dash_prefixed_host_before_subprocess() -> None:
    node = field_node()
    node.host = "-oProxyCommand=sh"

    with pytest.raises(SSHExecutionError):
        build_ssh_command(node, "snell", "status")


def test_run_remote_command_uses_subprocess_array_without_shell(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(command, **kwargs):
        calls.append({"command": command, **kwargs})
        return subprocess.CompletedProcess(command, 0, '{"ok": true, "data": {}, "error": null}', "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_remote_command(field_node(), "snell", "status", {"hello": "world"})

    assert result.returncode == 0
    assert result.parsed_json == {"ok": True, "data": {}, "error": None}
    assert calls[0]["command"] == build_ssh_command(field_node(), "snell", "status")
    assert calls[0]["input"] == '{"hello":"world"}'
    assert calls[0]["text"] is True
    assert calls[0]["capture_output"] is True
    assert calls[0]["timeout"] == 30
    assert "shell" not in calls[0]


def test_run_remote_command_captures_json_parse_errors(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "not json", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_remote_command(field_node(), "snell", "status", {})

    assert result.returncode == 0
    assert result.parsed_json is None
    assert result.json_error is not None


def test_run_remote_command_captures_timeouts(monkeypatch) -> None:
    def fake_run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, timeout=30)

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = run_remote_command(field_node(), "snell", "status", {})

    assert result.timed_out is True
    assert result.returncode is None
