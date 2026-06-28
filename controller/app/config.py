"""Configuration management for Multi-VPS Firewall Manager."""

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 7899


@dataclass
class SSHConfig:
    private_key_path: str = "/root/.ssh/snellmgr_ed25519"
    connect_timeout: int = 10
    command_timeout: int = 30


@dataclass
class SnellConfig:
    default_conf_path: str = "/root/snelldocker/snell-conf/snell.conf"


@dataclass
class BackupConfig:
    max_per_node: int = 20


@dataclass
class LogConfig:
    access_log_hours: int = 24


@dataclass
class AppConfig:
    server: ServerConfig = field(default_factory=ServerConfig)
    ssh: SSHConfig = field(default_factory=SSHConfig)
    snell: SnellConfig = field(default_factory=SnellConfig)
    backup: BackupConfig = field(default_factory=BackupConfig)
    log: LogConfig = field(default_factory=LogConfig)


def load_config(path: str = None) -> AppConfig:
    """Load configuration from YAML file with defaults."""
    if path is None:
        path = os.environ.get(
            "SNELL_CONFIG",
            str(Path(__file__).parent.parent / "config.yaml"),
        )

    config = AppConfig()

    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        section_map = {
            "server": (ServerConfig, "server"),
            "ssh": (SSHConfig, "ssh"),
            "snell": (SnellConfig, "snell"),
            "backup": (BackupConfig, "backup"),
            "log": (LogConfig, "log"),
        }

        for key, (cls, attr) in section_map.items():
            if key in data:
                setattr(config, attr, cls(**data[key]))

    return config
