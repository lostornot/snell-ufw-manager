from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def test_controller_service_binds_localhost_only() -> None:
    service = read("systemd/snell-ufw-control.service")

    assert "127.0.0.1" in service
    assert "8898" in service
    assert "/opt/snell-ufw-manager-by-gpt" in service
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

    assert "SOURCE_DIR=" in script
    assert "--exclude=.git" in script
    assert "--exclude=.venv" in script
    assert "--exclude=.env" in script
    assert "--exclude=data" in script
    assert "pyproject.toml" in script
    assert "rsync" in script
    assert "ADMIN_TOKEN" in script
    assert "SESSION_SECRET" in script
    assert "chmod 700" in script
    assert "chmod 600" in script
    assert "127.0.0.1" in script
    assert "/opt/snell-ufw-manager-by-gpt" in script


def test_package_declares_python_310_compatibility() -> None:
    pyproject = read("pyproject.toml")

    assert 'requires-python = ">=3.10"' in pyproject


def test_runtime_code_does_not_use_python_311_datetime_utc() -> None:
    runtime_files = [
        "app/locks.py",
        "app/services/candidates.py",
    ]

    for path in runtime_files:
        text = read(path)
        assert "from datetime import UTC" not in text
        assert "datetime.now(UTC)" not in text


def test_readme_documents_security_model() -> None:
    readme = read("README.md")

    assert "SSH Tunnel" in readme
    assert "ssh_alias" in readme
    assert "UFW inactive" in readme
    assert "Snell version" in readme
    assert "not a general VPS panel" in readme
