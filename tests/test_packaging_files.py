from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_controller_service_binds_localhost_only() -> None:
    service = read("systemd/snell-ufw-control.service")

    assert "127.0.0.1" in service
    assert "8898" in service
    assert "0.0.0.0" not in service


def test_node_installer_uses_single_restricted_nopasswd_entrypoint() -> None:
    script = read("scripts/install-node.sh")

    assert "NOPASSWD: /usr/local/sbin/snell-fwctl" in script
    assert "/usr/local/lib/snell-ufw-control/snellctl" in script
    assert "/usr/local/lib/snell-ufw-control/ufwctl" in script
    assert "/usr/local/lib/snell-ufw-control/systemctl" in script
    assert "visudo -cf" in script
    assert "chown root:root" in script
    assert "chmod 0755" in script


def test_controller_installer_generates_secrets_and_protects_data() -> None:
    script = read("scripts/install-controller.sh")

    assert "ADMIN_TOKEN" in script
    assert "SESSION_SECRET" in script
    assert "chmod 700" in script
    assert "chmod 600" in script
    assert "127.0.0.1" in script


def test_readme_documents_security_model() -> None:
    readme = read("README.md")

    assert "SSH Tunnel" in readme
    assert "ssh_alias" in readme
    assert "UFW inactive" in readme
    assert "Snell version" in readme
    assert "not a general VPS panel" in readme
