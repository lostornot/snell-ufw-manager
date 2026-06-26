from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import Any

from app.schemas import NodeCreate

REMOTE_ENTRYPOINT = "/usr/local/sbin/snell-fwctl"

ALLOWED_COMMANDS: dict[str, set[str]] = {
    "snell": {
        "install",
        "status",
        "start",
        "stop",
        "restart",
        "config-get",
        "config-apply",
        "logs",
        "backup",
        "restore",
    },
    "ufw": {
        "list",
        "apply",
        "backup",
        "restore",
        "candidates",
        "enable",
    },
    "system": {
        "check",
    },
}


class SSHExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class SSHCommandResult:
    returncode: int | None
    stdout: str
    stderr: str
    parsed_json: Any | None
    timed_out: bool = False
    json_error: str | None = None


def _reject_dash_prefixed(name: str, value: str | None) -> None:
    if value and value.startswith("-"):
        raise SSHExecutionError(f"{name} must not begin with '-'")


def _validate_remote_command(namespace: str, subcommand: str) -> None:
    allowed = ALLOWED_COMMANDS.get(namespace)
    if allowed is None:
        raise SSHExecutionError(f"unsupported namespace: {namespace}")
    if subcommand not in allowed:
        raise SSHExecutionError(f"unsupported subcommand for {namespace}: {subcommand}")


def build_ssh_command(node: NodeCreate, namespace: str, subcommand: str) -> list[str]:
    _validate_remote_command(namespace, subcommand)
    _reject_dash_prefixed("ssh_alias", node.ssh_alias)
    _reject_dash_prefixed("host", node.host)
    _reject_dash_prefixed("ssh_key_path", node.ssh_key_path)

    if node.ssh_alias:
        return [
            "ssh",
            node.ssh_alias,
            "sudo",
            REMOTE_ENTRYPOINT,
            namespace,
            subcommand,
        ]

    if not node.host or not node.ssh_user or node.ssh_port is None:
        raise SSHExecutionError("field-based SSH requires host, ssh_user, and ssh_port")

    command = ["ssh"]
    if node.ssh_key_path:
        command.extend(["-i", node.ssh_key_path])
    command.extend(
        [
            "-p",
            str(node.ssh_port),
            f"{node.ssh_user}@{node.host}",
            "sudo",
            REMOTE_ENTRYPOINT,
            namespace,
            subcommand,
        ]
    )
    return command


def run_remote_command(
    node: NodeCreate,
    namespace: str,
    subcommand: str,
    payload: dict[str, Any] | list[Any] | None,
) -> SSHCommandResult:
    command = build_ssh_command(node, namespace, subcommand)
    json_payload = json.dumps(payload or {}, separators=(",", ":"))
    try:
        completed = subprocess.run(
            command,
            input=json_payload,
            text=True,
            capture_output=True,
            timeout=node.connect_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return SSHCommandResult(
            returncode=None,
            stdout=exc.stdout or "",
            stderr=exc.stderr or "",
            parsed_json=None,
            timed_out=True,
        )

    parsed_json: Any | None = None
    json_error: str | None = None
    if completed.stdout:
        try:
            parsed_json = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            json_error = str(exc)

    return SSHCommandResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        parsed_json=parsed_json,
        json_error=json_error,
    )
