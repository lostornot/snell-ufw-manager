from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas import (
    NodeCreate,
    RelayIPCreate,
    SnellConfigProfileCreate,
)


def valid_node_payload() -> dict[str, object]:
    return {
        "name": "Tokyo 1",
        "host": "203.0.113.10",
        "ssh_port": 22,
        "ssh_user": "snellmgr",
        "snell_port": 23456,
        "enable_tcp": True,
        "enable_udp": True,
        "psk": "shared-secret",
        "desired_config_text": "listen = ::0:23456\npsk = shared-secret\n",
    }


def test_valid_node_payload_is_accepted() -> None:
    node = NodeCreate(**valid_node_payload())

    assert node.host == "203.0.113.10"
    assert node.ssh_user == "snellmgr"
    assert node.enable_tcp is True
    assert node.enable_udp is True


@pytest.mark.parametrize("field", ["ssh_port", "snell_port"])
@pytest.mark.parametrize("value", [0, 65536])
def test_ports_must_be_in_tcp_udp_range(field: str, value: int) -> None:
    payload = valid_node_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


@pytest.mark.parametrize("bad_user", ["root;reboot", "../root", "-snellmgr", "name with space"])
def test_ssh_user_uses_conservative_linux_username_pattern(bad_user: str) -> None:
    payload = valid_node_payload()
    payload["ssh_user"] = bad_user

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


@pytest.mark.parametrize("field", ["host", "ssh_alias"])
def test_host_like_values_cannot_begin_with_dash(field: str) -> None:
    payload = valid_node_payload()
    payload[field] = "-oProxyCommand=sh"

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


def test_node_requires_host_or_ssh_alias() -> None:
    payload = valid_node_payload()
    payload["host"] = None

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


def test_alias_based_node_does_not_require_host_user_or_port() -> None:
    payload = valid_node_payload()
    payload["ssh_alias"] = "tokyo-snell"
    payload["host"] = None
    payload["ssh_user"] = None
    payload["ssh_port"] = None

    node = NodeCreate(**payload)

    assert node.ssh_alias == "tokyo-snell"
    assert node.host is None


def test_at_least_one_protocol_must_be_enabled() -> None:
    payload = valid_node_payload()
    payload["enable_tcp"] = False
    payload["enable_udp"] = False

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


@pytest.mark.parametrize("value", ["198.51.100.8", "198.51.100.0/24", "2001:db8::/64"])
def test_relay_ip_accepts_ip_or_cidr(value: str) -> None:
    relay_ip = RelayIPCreate(relay_group_id=1, value=value)

    assert relay_ip.value == value


@pytest.mark.parametrize("value", ["not an ip", "999.1.1.1", "198.51.100.0/99"])
def test_relay_ip_rejects_invalid_ip_or_cidr(value: str) -> None:
    with pytest.raises(ValidationError):
        RelayIPCreate(relay_group_id=1, value=value)


def test_private_key_material_is_not_accepted_as_node_input() -> None:
    payload = valid_node_payload()
    payload["private_key"] = "-----BEGIN OPENSSH PRIVATE KEY-----"

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


def test_key_passphrase_is_not_accepted_as_node_input() -> None:
    payload = valid_node_payload()
    payload["ssh_key_passphrase"] = "secret"

    with pytest.raises(ValidationError):
        NodeCreate(**payload)


def test_profile_uses_same_protocol_validation() -> None:
    with pytest.raises(ValidationError):
        SnellConfigProfileCreate(
            name="bad",
            snell_port=23456,
            enable_tcp=False,
            enable_udp=False,
            psk="secret",
            config_text="listen = ::0:23456\npsk = secret\n",
        )

