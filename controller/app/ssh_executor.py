"""SSH executor for remote snell-fwctl commands."""

import asyncio
import json
import logging
from pathlib import Path

import asyncssh

from config import AppConfig

logger = logging.getLogger(__name__)


class SSHExecutor:
    """Execute snell-fwctl commands on remote nodes via SSH."""

    def __init__(self, config: AppConfig):
        self.config = config

    async def run(self, node: dict, command: str) -> dict:
        """Execute a nft-fwctl command on a node and return parsed JSON."""
        full_cmd = f"sudo /usr/local/sbin/nft-fwctl {command}"
        logger.info("SSH %s@%s: %s", node.get("ssh_user", "snellmgr"), node["host"], full_cmd)

        try:
            async with asyncssh.connect(
                node["host"],
                port=node.get("ssh_port", 22),
                username=node.get("ssh_user", "snellmgr"),
                client_keys=[self.config.ssh.private_key_path],
                known_hosts=None,
                connect_timeout=self.config.ssh.connect_timeout,
            ) as conn:
                result = await asyncio.wait_for(
                    conn.run(full_cmd),
                    timeout=self.config.ssh.command_timeout,
                )

                stdout = result.stdout.strip() if result.stdout else ""
                stderr = result.stderr.strip() if result.stderr else ""

                if result.exit_status != 0:
                    return {
                        "ok": False,
                        "error": f"Exit code {result.exit_status}: {stderr or stdout}",
                    }

                if not stdout:
                    return {"ok": False, "error": "Empty response from node"}

                return json.loads(stdout)

        except asyncssh.DisconnectError as exc:
            return {"ok": False, "error": f"SSH disconnect: {exc}"}
        except asyncssh.PermissionDenied as exc:
            return {"ok": False, "error": f"SSH permission denied: {exc}"}
        except asyncssh.Error as exc:
            return {"ok": False, "error": f"SSH error: {exc}"}
        except json.JSONDecodeError:
            return {"ok": False, "error": f"Invalid JSON from node: {stdout[:200]}"}
        except asyncio.TimeoutError:
            return {"ok": False, "error": f"Command timed out ({self.config.ssh.command_timeout}s)"}
        except OSError as exc:
            return {"ok": False, "error": f"Connection failed: {exc}"}
        except Exception as exc:
            logger.exception("Unexpected error running SSH command")
            return {"ok": False, "error": str(exc)}

    # -- Convenience methods --------------------------------------------------

    async def test_connection(self, node: dict) -> dict:
        """Test SSH connectivity and nft-fwctl availability."""
        return await self.run(node, "status")

    async def detect_environment(self, node: dict) -> dict:
        """Detect remote VPS SSH, Snell, Docker, and Tailscale environments."""
        return await self.run(node, "detect")

    async def plan_policy(self, node: dict, policy_json: str) -> dict:
        """Get dry-run ruleset plan based on policy JSON."""
        # Escape quotes in JSON to pass via command line parameter
        escaped_json = policy_json.replace("'", "'\\''")
        return await self.run(node, f"plan '{escaped_json}'")

    async def apply_policy(self, node: dict, policy_json: str) -> dict:
        """Temporarily apply ruleset based on policy JSON (needs confirm to persist)."""
        escaped_json = policy_json.replace("'", "'\\''")
        return await self.run(node, f"apply '{escaped_json}'")

    async def confirm_policy(self, node: dict) -> dict:
        """Confirm temporarily applied policy to make it persisted."""
        return await self.run(node, "confirm")

    async def get_whitelist(self, node: dict) -> dict:
        """Get all UFW rules on the node (mocked interface for compatibility)."""
        return await self.run(node, "candidates")

    async def get_candidates(self, node: dict, hours: int = 24, port: str | None = None) -> dict:
        """Get recent IPs that tried to access ports from nft log."""
        query_port = port if port is not None else "all"
        return await self.run(node, f"candidates {query_port} {hours}")

    async def get_snell_port(self, node: dict) -> dict:
        """Read Snell port from the node's config file."""
        conf = node.get("snell_conf", self.config.snell.default_conf_path)
        return await self.run(node, f"port {conf}")

    async def backup(self, node: dict) -> dict:
        """Trigger a rules backup on the node."""
        return await self.run(node, "backup")

    async def get_backups(self, node: dict) -> dict:
        """List available backups on the node."""
        return await self.run(node, "backups")

    def get_public_key(self) -> str:
        """Read the SSH public key used to connect to nodes."""
        key_path = Path(self.config.ssh.private_key_path + ".pub")
        try:
            return key_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return ""

    def get_controller_ip(self) -> str:
        """Best-effort guess of this machine's public IP (for setup script)."""
        import socket
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "<控制中心IP>"
