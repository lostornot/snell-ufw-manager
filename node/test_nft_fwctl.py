import subprocess
import json
import os
import sys

def run_nft_fwctl(args):
    # 使用 bash 显式调用 node/nft-fwctl
    script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nft-fwctl")
    res = subprocess.run(["bash", script_path] + args, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr

def test_status():
    code, stdout, stderr = run_nft_fwctl(["status"])
    assert code == 0, f"Failed with stderr: {stderr}"
    data = json.loads(stdout)
    assert data["ok"] is True
    assert "backend" in data
    assert data["backend"] == "nftables"
    assert "nftables_installed" in data

def test_detect():
    code, stdout, stderr = run_nft_fwctl(["detect"])
    assert code == 0, f"Failed with stderr: {stderr}"
    data = json.loads(stdout)
    assert data["ok"] is True
    assert "ssh" in data
    assert "snell" in data
    assert "docker" in data
    assert "tailscale" in data

def test_invalid_command():
    code, stdout, stderr = run_nft_fwctl(["nonexistent_command"])
    # 按照旧脚本的错误格式设计，错误返回应该也是 ok: false, exit 1
    assert code == 1 or code == 255
    data = json.loads(stdout or stderr)
    assert data["ok"] is False
    assert "unknown command" in data["error"]
