import asyncio
import os
import tempfile
import aiosqlite
import sys

# 确保能导入同级 database 模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import pytest
from app.database import init_db, get_db_path

@pytest.mark.asyncio
async def test_migration():
    temp_db = tempfile.mktemp(suffix=".db")
    # 临时覆盖全局 SNELL_DB 环境变量以进行测试隔离
    os.environ["SNELL_DB"] = temp_db
    try:
        # 执行初始化数据库
        await init_db()
        
        async with aiosqlite.connect(temp_db) as db:
            # 1. 验证 nodes 表是否包含新增字段
            cursor = await db.execute("PRAGMA table_info(nodes)")
            cols = [row[1] for row in await cursor.fetchall()]
            required_node_cols = [
                "firewall_backend",
                "role",
                "tailscale_ip",
                "docker_detected",
                "docker_risk",
                "nftables_active",
                "last_checked_at"
            ]
            for col in required_node_cols:
                assert col in cols, f"Missing required column in nodes: {col}"
            
            # 2. 验证 ip_addresses 表是否包含新增字段
            cursor = await db.execute("PRAGMA table_info(ip_addresses)")
            ip_cols = [row[1] for row in await cursor.fetchall()]
            required_ip_cols = [
                "set_name",
                "label",
                "expires_at",
                "enabled"
            ]
            for col in required_ip_cols:
                assert col in ip_cols, f"Missing required column in ip_addresses: {col}"

            # 3. 验证 policies 表是否存在
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='policies'"
            )
            assert await cursor.fetchone() is not None, "Table 'policies' does not exist"
            
            # 4. 验证 node_policies 表是否存在
            cursor = await db.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='node_policies'"
            )
            assert await cursor.fetchone() is not None, "Table 'node_policies' does not exist"

        print("DATABASE MIGRATION TEST: PASS")
    except Exception as e:
        print(f"DATABASE MIGRATION TEST: FAIL - {e}", file=sys.stderr)
        raise e
    finally:
        if os.path.exists(temp_db):
            try:
                os.remove(temp_db)
            except OSError:
                pass

if __name__ == "__main__":
    asyncio.run(test_migration())
