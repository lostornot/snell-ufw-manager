from __future__ import annotations

import pytest

from app.services.nodes import ensure_pinned_snell_version, render_snell_config


def test_render_snell_config_uses_port_and_psk() -> None:
    config = render_snell_config(snell_port=23456, psk="secret")

    assert "listen = ::0:23456" in config
    assert "psk = secret" in config


@pytest.mark.parametrize("version", [None, "", "latest"])
def test_rejects_implicit_latest_versions(version: str | None) -> None:
    with pytest.raises(ValueError):
        ensure_pinned_snell_version(version)


@pytest.mark.parametrize("version", ["v4.1.1", "v5.x", "/opt/snell/snell-server"])
def test_accepts_explicit_versions_or_controlled_binary_path(version: str) -> None:
    assert ensure_pinned_snell_version(version) == version

