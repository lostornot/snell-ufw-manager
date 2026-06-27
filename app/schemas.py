from __future__ import annotations

import ipaddress
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


USERNAME_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,31}$")
SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


class StrictSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProtocolFlags(StrictSchema):
    enable_tcp: bool = True
    enable_udp: bool = True

    @model_validator(mode="after")
    def require_at_least_one_protocol(self) -> ProtocolFlags:
        if not self.enable_tcp and not self.enable_udp:
            raise ValueError("at least one protocol must be enabled")
        return self


class NodeCreate(ProtocolFlags):
    name: str = Field(min_length=1, max_length=120)
    host: str | None = Field(default=None, max_length=255)
    ssh_alias: str | None = Field(default=None, max_length=120)
    ssh_port: int | None = Field(default=22, ge=1, le=65535)
    ssh_user: str | None = Field(default="snellmgr", max_length=64)
    ssh_key_path: str | None = Field(default=None, max_length=512)
    connect_timeout: int = Field(default=30, ge=1, le=300)
    snell_port: int = Field(ge=1, le=65535)
    snell_version: str | None = Field(default=None, max_length=64)
    snell_channel: str | None = Field(default=None, max_length=64)
    snell_arch: str | None = Field(default=None, max_length=64)
    snell_sha256: str | None = Field(default=None, max_length=64)
    remark: str | None = None
    enabled: bool = True
    desired_config_text: str | None = None
    psk: str | None = Field(default=None, max_length=512)

    @field_validator("host", "ssh_alias", "ssh_key_path")
    @classmethod
    def reject_dash_prefixed_values(cls, value: str | None) -> str | None:
        if value is not None and value.startswith("-"):
            raise ValueError("value must not begin with '-'")
        return value

    @field_validator("ssh_user")
    @classmethod
    def validate_ssh_user(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not USERNAME_RE.fullmatch(value):
            raise ValueError("ssh_user must be a conservative Linux username")
        return value

    @field_validator("snell_sha256")
    @classmethod
    def validate_snell_sha256(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_RE.fullmatch(value):
            raise ValueError("snell_sha256 must be a 64 character hex SHA256 digest")
        return value.lower() if value is not None else None

    @model_validator(mode="after")
    def validate_connection_fields(self) -> NodeCreate:
        if self.ssh_alias:
            return self
        if not self.host:
            raise ValueError("host is required when ssh_alias is not set")
        if not self.ssh_user:
            raise ValueError("ssh_user is required when ssh_alias is not set")
        if self.ssh_port is None:
            raise ValueError("ssh_port is required when ssh_alias is not set")
        return self


class SnellConfigProfileCreate(ProtocolFlags):
    name: str = Field(min_length=1, max_length=120)
    snell_port: int = Field(ge=1, le=65535)
    snell_version: str | None = Field(default=None, max_length=64)
    snell_channel: str | None = Field(default=None, max_length=64)
    snell_arch: str | None = Field(default=None, max_length=64)
    snell_sha256: str | None = Field(default=None, max_length=64)
    psk: str | None = Field(default=None, max_length=512)
    config_text: str | None = None
    remark: str | None = None

    @field_validator("snell_sha256")
    @classmethod
    def validate_snell_sha256(cls, value: str | None) -> str | None:
        if value is not None and not SHA256_RE.fullmatch(value):
            raise ValueError("snell_sha256 must be a 64 character hex SHA256 digest")
        return value.lower() if value is not None else None


class RelayGroupCreate(StrictSchema):
    name: str = Field(min_length=1, max_length=120)
    remark: str | None = None


class RelayIPCreate(StrictSchema):
    relay_group_id: int = Field(ge=1)
    value: str
    remark: str | None = None

    @field_validator("value")
    @classmethod
    def validate_ip_or_cidr(cls, value: str) -> str:
        try:
            ipaddress.ip_network(value, strict=False)
        except ValueError as exc:
            raise ValueError("value must be an IP address or CIDR") from exc
        return value


class NodePolicyCreate(StrictSchema):
    node_id: int = Field(ge=1)
    relay_group_id: int = Field(ge=1)
    enabled: bool = True


class AuditLogCreate(StrictSchema):
    actor: str
    action: str
    target_type: str | None = None
    target_id: int | None = None
    summary: str
    request_json: dict[str, Any] | list[Any] | None = None
    result_json: dict[str, Any] | list[Any] | None = None
    success: bool
    error: str | None = None
