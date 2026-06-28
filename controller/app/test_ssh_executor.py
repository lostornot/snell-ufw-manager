import asyncio
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

# 将 controller 目录添加到 path 中以满足绝对包导入
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.ssh_executor import SSHExecutor
from app.config import load_config

@pytest.mark.asyncio
async def test_ssh_executor_calls_nft_fwctl():
    config = load_config()
    executor = SSHExecutor(config)
    
    # 模拟 node 数据
    node = {
        "host": "1.2.3.4",
        "ssh_port": 22,
        "ssh_user": "snellmgr",
        "snell_port": 28261
    }
    
    # 模拟 asyncssh 执行
    with patch("asyncssh.connect") as mock_connect:
        mock_conn = AsyncMock()
        mock_connect.return_value.__aenter__.return_value = mock_conn
        
        mock_result = AsyncMock()
        mock_result.exit_status = 0
        mock_result.stdout = '{"ok": true, "backend": "nftables", "nftables_installed": true}'
        mock_result.stderr = ''
        mock_conn.run.return_value = mock_result
        
        res = await executor.run(node, "status")
        
        assert res["ok"] is True
        assert res["backend"] == "nftables"
        mock_conn.run.assert_called_once_with("sudo /usr/local/sbin/nft-fwctl status")
