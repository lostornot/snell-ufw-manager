"""SQLite database layer for Snell UFW Manager."""

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

CREATE TABLE IF NOT EXISTS relay_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    remark      TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relay_ips (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES relay_groups(id) ON DELETE CASCADE,
    ip_cidr     TEXT NOT NULL,
    note        TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(group_id, ip_cidr)
);

CREATE TABLE IF NOT EXISTS node_relay_groups (
    node_id     INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    group_id    INTEGER NOT NULL REFERENCES relay_groups(id) ON DELETE CASCADE,
    PRIMARY KEY (node_id, group_id)
);

CREATE TABLE IF NOT EXISTS op_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
    node_name   TEXT,
    action      TEXT NOT NULL,
    target      TEXT,
    detail      TEXT,
    success     INTEGER,
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
        await db.execute("PRAGMA foreign_keys=ON")
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
# Relay Groups
# ---------------------------------------------------------------------------

async def get_all_relay_groups() -> list[dict]:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute("SELECT * FROM relay_groups ORDER BY id")
        groups = [dict(row) for row in await cursor.fetchall()]
        for group in groups:
            cursor = await db.execute(
                "SELECT * FROM relay_ips WHERE group_id = ? ORDER BY id",
                (group["id"],),
            )
            group["ips"] = [dict(row) for row in await cursor.fetchall()]
            cursor = await db.execute(
                """SELECT n.id, n.name FROM nodes n
                   JOIN node_relay_groups nrg ON n.id = nrg.node_id
                   WHERE nrg.group_id = ?""",
                (group["id"],),
            )
            group["nodes"] = [dict(row) for row in await cursor.fetchall()]
        return groups


async def get_relay_group(group_id: int) -> dict | None:
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM relay_groups WHERE id = ?", (group_id,)
        )
        group = await cursor.fetchone()
        if not group:
            return None
        group = dict(group)
        cursor = await db.execute(
            "SELECT * FROM relay_ips WHERE group_id = ? ORDER BY id",
            (group_id,),
        )
        group["ips"] = [dict(row) for row in await cursor.fetchall()]
        cursor = await db.execute(
            """SELECT n.id, n.name FROM nodes n
               JOIN node_relay_groups nrg ON n.id = nrg.node_id
               WHERE nrg.group_id = ?""",
            (group_id,),
        )
        group["nodes"] = [dict(row) for row in await cursor.fetchall()]
        return group


async def create_relay_group(name: str, remark: str = "") -> int:
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO relay_groups (name, remark) VALUES (?, ?)",
            (name, remark),
        )
        await db.commit()
        return cursor.lastrowid


async def update_relay_group(group_id: int, **kwargs) -> None:
    if not kwargs:
        return
    async with _get_db() as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [group_id]
        await db.execute(f"UPDATE relay_groups SET {sets} WHERE id = ?", values)
        await db.commit()


async def delete_relay_group(group_id: int) -> None:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute("DELETE FROM relay_groups WHERE id = ?", (group_id,))
        await db.commit()


async def add_relay_ip(group_id: int, ip_cidr: str, note: str = "") -> int:
    async with _get_db() as db:
        cursor = await db.execute(
            "INSERT INTO relay_ips (group_id, ip_cidr, note) VALUES (?, ?, ?)",
            (group_id, ip_cidr, note),
        )
        await db.commit()
        return cursor.lastrowid


async def delete_relay_ip(ip_id: int) -> None:
    async with _get_db() as db:
        await db.execute("DELETE FROM relay_ips WHERE id = ?", (ip_id,))
        await db.commit()


async def update_relay_ip(ip_id: int, **kwargs) -> None:
    if not kwargs:
        return
    async with _get_db() as db:
        sets = ", ".join(f"{k} = ?" for k in kwargs)
        values = list(kwargs.values()) + [ip_id]
        await db.execute(f"UPDATE relay_ips SET {sets} WHERE id = ?", values)
        await db.commit()


# ---------------------------------------------------------------------------
# Node ↔ Relay Group Associations
# ---------------------------------------------------------------------------

async def get_node_relay_group_ids(node_id: int) -> list[int]:
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT group_id FROM node_relay_groups WHERE node_id = ?",
            (node_id,),
        )
        return [row[0] for row in await cursor.fetchall()]


async def set_node_relay_groups(node_id: int, group_ids: list[int]) -> None:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        await db.execute(
            "DELETE FROM node_relay_groups WHERE node_id = ?", (node_id,)
        )
        for gid in group_ids:
            await db.execute(
                "INSERT OR IGNORE INTO node_relay_groups (node_id, group_id) VALUES (?, ?)",
                (node_id, gid),
            )
        await db.commit()


async def get_node_allowed_ips(node_id: int) -> list[dict]:
    """Get all IPs that should be allowed on this node (from all associated relay groups)."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT DISTINCT ri.ip_cidr, ri.note, rg.name AS group_name
               FROM relay_ips ri
               JOIN relay_groups rg ON ri.group_id = rg.id
               JOIN node_relay_groups nrg ON rg.id = nrg.group_id
               WHERE nrg.node_id = ?
               ORDER BY rg.name, ri.ip_cidr""",
            (node_id,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_groups_for_ip(ip_cidr: str) -> list[dict]:
    """Find which groups contain a given IP."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT rg.id, rg.name FROM relay_groups rg
               JOIN relay_ips ri ON rg.id = ri.group_id
               WHERE ri.ip_cidr = ?""",
            (ip_cidr,),
        )
        return [dict(row) for row in await cursor.fetchall()]


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
