from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class Node(TimestampMixin, Base):
    __tablename__ = "nodes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    host: Mapped[str | None] = mapped_column(String(255), nullable=True)
    ssh_alias: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ssh_port: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ssh_user: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ssh_key_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    connect_timeout: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    snell_port: Mapped[int] = mapped_column(Integer, nullable=False)
    snell_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snell_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snell_arch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enable_tcp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_udp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    desired_config_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    psk: Mapped[str | None] = mapped_column(String(512), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    policies: Mapped[list[NodePolicy]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )
    candidates: Mapped[list[AccessCandidate]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )
    locks: Mapped[list[OperationLock]] = relationship(
        back_populates="node",
        cascade="all, delete-orphan",
    )


class SnellConfigProfile(TimestampMixin, Base):
    __tablename__ = "snell_config_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    snell_port: Mapped[int] = mapped_column(Integer, nullable=False)
    snell_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snell_channel: Mapped[str | None] = mapped_column(String(64), nullable=True)
    snell_arch: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enable_tcp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enable_udp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    psk: Mapped[str | None] = mapped_column(String(512), nullable=True)
    config_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class RelayGroup(TimestampMixin, Base):
    __tablename__ = "relay_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)

    relay_ips: Mapped[list[RelayIP]] = relationship(
        back_populates="relay_group",
        cascade="all, delete-orphan",
    )
    policies: Mapped[list[NodePolicy]] = relationship(
        back_populates="relay_group",
        cascade="all, delete-orphan",
    )


class RelayIP(Base):
    __tablename__ = "relay_ips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    relay_group_id: Mapped[int] = mapped_column(ForeignKey("relay_groups.id"), nullable=False)
    value: Mapped[str] = mapped_column(String(64), nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    relay_group: Mapped[RelayGroup] = relationship(back_populates="relay_ips")


class NodePolicy(TimestampMixin, Base):
    __tablename__ = "node_policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    relay_group_id: Mapped[int] = mapped_column(ForeignKey("relay_groups.id"), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    node: Mapped[Node] = relationship(back_populates="policies")
    relay_group: Mapped[RelayGroup] = relationship(back_populates="policies")


class AccessCandidate(Base):
    __tablename__ = "access_candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), nullable=False)
    ip: Mapped[str] = mapped_column(String(64), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[str] = mapped_column(String(8), nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    promoted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    promoted_relay_group_id: Mapped[int | None] = mapped_column(
        ForeignKey("relay_groups.id"),
        nullable=True,
    )

    node: Mapped[Node] = relationship(back_populates="candidates")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    request_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class OperationLock(Base):
    __tablename__ = "operation_locks"

    node_id: Mapped[int] = mapped_column(ForeignKey("nodes.id"), primary_key=True)
    operation_type: Mapped[str] = mapped_column(String(120), nullable=False)
    locked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    owner: Mapped[str] = mapped_column(String(120), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    node: Mapped[Node] = relationship(back_populates="locks")

