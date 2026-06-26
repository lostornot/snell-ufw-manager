"""SQLite database layer for VPS UFW Firewall Manager."""

import os
from pathlib import Path
import aiosqlite

DB_PATH = os.environ.get(
    "SNELL_DB",
    str(Path(__file__).parent.parent / "data" / "snell_manager.db"),
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL,
    ssh_port    INTEGER DEFAULT 22,
    ssh_user    TEXT DEFAULT 'snellmgr',
    snell_port  INTEGER NOT NULL,
    snell_conf  TEXT DEFAULT '/root/snelldocker/snell-conf/snell.conf',
    remark      TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ip_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    remark      TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ip_group_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES ip_groups(id) ON DELETE CASCADE,
    ip_cidr     TEXT NOT NULL,
    note        TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(group_id, ip_cidr)
);

CREATE TABLE IF NOT EXISTS op_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
    node_name   TEXT,
    action      TEXT NOT NULL,
    target      TEXT,
    detail      TEXT,
    success     INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
"""


async def init_db():
    """Initialize the database and create tables."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA)
        await db.commit()


def _get_db():
    """Get a database connection (caller must use as async context manager)."""
    return aiosqlite.connect(DB_PATH)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def get_all_nodes() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM nodes ORDER BY id")
        return [dict(row) for row in await cursor.fetchall()]


async def get_node(node_id: int) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM nodes WHERE id = ?", (node_id,))
        row = await cursor.fetchone()
        return dict(row) if row else None


async def create_node(
    name: str,
    host: str,
    ssh_port: int,
    ssh_user: str,
    snell_port: int,
    snell_conf: str,
    remark: str = "",
) -> int:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            """INSERT INTO nodes (name, host, ssh_port, ssh_user, snell_port, snell_conf, remark)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, host, ssh_port, ssh_user, snell_port, snell_conf, remark),
        )
        await db.commit()
        return cursor.lastrowid


async def update_node(node_id: int, **kwargs) -> None:
    if not kwargs:
        return
    async with _get_db() as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [node_id]
        await db.execute(f"UPDATE nodes SET {sets} WHERE id = ?", values)
        await db.commit()


async def delete_node(node_id: int) -> None:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM nodes WHERE id = ?", (node_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# IP Groups
# ---------------------------------------------------------------------------

async def get_all_ip_groups() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM ip_groups ORDER BY id")
        groups = [dict(row) for row in await cursor.fetchall()]
        for group in groups:
            cursor = await db.execute(
                "SELECT * FROM ip_group_items WHERE group_id = ? ORDER BY id",
                (group["id"],),
            )
            group["ips"] = [dict(row) for row in await cursor.fetchall()]
        return groups


async def get_ip_group(group_id: int) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ip_groups WHERE id = ?", (group_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        group = dict(row)
        cursor = await db.execute(
            "SELECT * FROM ip_group_items WHERE group_id = ? ORDER BY id",
            (group_id,),
        )
        group["ips"] = [dict(row) for row in await cursor.fetchall()]
        return group


async def create_ip_group(name: str, remark: str = "") -> int:
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO ip_groups (name, remark) VALUES (?, ?)",
            (name, remark),
        )
        await db.commit()
        return cursor.lastrowid


async def update_ip_group(group_id: int, **kwargs) -> None:
    if not kwargs:
        return
    async with _get_db() as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [group_id]
        await db.execute(f"UPDATE ip_groups SET {sets} WHERE id = ?", values)
        await db.commit()


async def delete_ip_group(group_id: int) -> None:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM ip_groups WHERE id = ?", (group_id,))
        await db.commit()


async def add_ip_group_item(group_id: int, ip_cidr: str, note: str = "") -> int:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            "INSERT INTO ip_group_items (group_id, ip_cidr, note) VALUES (?, ?, ?)",
            (group_id, ip_cidr, note),
        )
        await db.commit()
        return cursor.lastrowid


async def delete_ip_group_item(item_id: int) -> None:
    async with _get_db() as db:
        await db.execute("DELETE FROM ip_group_items WHERE id = ?", (item_id,))
        await db.commit()


# ---------------------------------------------------------------------------
# Operation Logs
# ---------------------------------------------------------------------------

async def add_op_log(
    node_id: int | None,
    node_name: str,
    action: str,
    target: str = "",
    detail: str = "",
    success: bool = True,
) -> None:
    async with _get_db() as db:
        await db.execute(
            """INSERT INTO op_logs (node_id, node_name, action, target, detail, success)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (node_id, node_name, action, target, detail, 1 if success else 0),
        )
        await db.commit()


async def get_op_logs(node_id: int | None = None, limit: int = 50) -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        if node_id:
            cursor = await db.execute(
                "SELECT * FROM op_logs WHERE node_id = ? ORDER BY id DESC LIMIT ?",
                (node_id, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM op_logs ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return [dict(row) for row in await cursor.fetchall()]
