"""SQLite database layer for VPS UFW Firewall Manager."""

import logging
import os
from pathlib import Path
import aiosqlite

def get_db_path() -> str:
    return os.environ.get(
        "SNELL_DB",
        str(Path(__file__).parent.parent / "data" / "snell_manager.db"),
    )

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS nodes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    host            TEXT NOT NULL,
    ssh_port        INTEGER DEFAULT 22,
    ssh_user        TEXT DEFAULT 'snellmgr',
    snell_port      INTEGER NOT NULL,
    snell_conf      TEXT DEFAULT '/root/snelldocker/snell-conf/snell.conf',
    remark          TEXT DEFAULT '',
    enabled         INTEGER DEFAULT 1,
    country         TEXT DEFAULT '',
    country_code    TEXT DEFAULT '',
    tags            TEXT DEFAULT '',
    firewall_backend TEXT DEFAULT 'nftables',
    role            TEXT DEFAULT '',
    tailscale_ip    TEXT DEFAULT '',
    docker_detected INTEGER DEFAULT 0,
    docker_risk     TEXT DEFAULT '',
    nftables_active INTEGER DEFAULT 0,
    last_checked_at TEXT DEFAULT '',
    created_at      TEXT DEFAULT (datetime('now'))
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

CREATE TABLE IF NOT EXISTS ip_addresses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ip_cidr     TEXT NOT NULL UNIQUE,
    tag         TEXT DEFAULT '',
    source      TEXT DEFAULT 'manual',
    set_name    TEXT DEFAULT '',
    label       TEXT DEFAULT '',
    expires_at  TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now')),
    updated_at  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS policies (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    service         TEXT NOT NULL,
    port            INTEGER NOT NULL,
    protocol        TEXT NOT NULL,
    allow_sets      TEXT NOT NULL,
    default_action  TEXT DEFAULT 'drop',
    enabled         INTEGER DEFAULT 1,
    created_at      TEXT DEFAULT (datetime('now')),
    updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS node_policies (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id             INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    policy_id           INTEGER NOT NULL REFERENCES policies(id) ON DELETE CASCADE,
    enabled             INTEGER DEFAULT 1,
    last_applied_at     TEXT DEFAULT '',
    last_apply_status   TEXT DEFAULT '',
    last_error          TEXT DEFAULT '',
    UNIQUE(node_id, policy_id)
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

CREATE TABLE IF NOT EXISTS ip_geo_cache (
    ip           TEXT PRIMARY KEY,
    country      TEXT DEFAULT '',
    country_code TEXT DEFAULT '',
    city         TEXT DEFAULT '',
    asn          TEXT DEFAULT '',
    created_at   TEXT DEFAULT (datetime('now'))
);
"""


async def init_db():
    """Initialize the database and create tables."""
    db_path = get_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    async with aiosqlite.connect(db_path) as db:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        await db.executescript(SCHEMA)
        
        # Dynamic schema upgrades for nodes table
        cursor = await db.execute("PRAGMA table_info(nodes)")
        cols = [row[1] for row in await cursor.fetchall()]
        
        # Older columns
        if "country" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN country TEXT DEFAULT ''")
        if "country_code" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN country_code TEXT DEFAULT ''")
        if "tags" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN tags TEXT DEFAULT ''")
            
        # New columns for nftables/docker detection
        if "firewall_backend" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN firewall_backend TEXT DEFAULT 'nftables'")
        if "role" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN role TEXT DEFAULT ''")
        if "tailscale_ip" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN tailscale_ip TEXT DEFAULT ''")
        if "docker_detected" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN docker_detected INTEGER DEFAULT 0")
        if "docker_risk" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN docker_risk TEXT DEFAULT ''")
        if "nftables_active" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN nftables_active INTEGER DEFAULT 0")
        if "last_checked_at" not in cols:
            await db.execute("ALTER TABLE nodes ADD COLUMN last_checked_at TEXT DEFAULT ''")

        # Dynamic schema upgrades for ip_addresses table
        cursor = await db.execute("PRAGMA table_info(ip_addresses)")
        ip_cols = [row[1] for row in await cursor.fetchall()]
        if "set_name" not in ip_cols:
            await db.execute("ALTER TABLE ip_addresses ADD COLUMN set_name TEXT DEFAULT ''")
        if "label" not in ip_cols:
            await db.execute("ALTER TABLE ip_addresses ADD COLUMN label TEXT DEFAULT ''")
        if "expires_at" not in ip_cols:
            await db.execute("ALTER TABLE ip_addresses ADD COLUMN expires_at TEXT DEFAULT ''")
        if "enabled" not in ip_cols:
            await db.execute("ALTER TABLE ip_addresses ADD COLUMN enabled INTEGER DEFAULT 1")

        # --- Migrate legacy ip_groups + ip_group_items → ip_addresses ---
        try:
            cursor = await db.execute(
                "SELECT COUNT(*) FROM ip_group_items"
            )
            legacy_count = (await cursor.fetchone())[0]

            cursor = await db.execute(
                "SELECT COUNT(*) FROM ip_addresses WHERE source = 'migrated'"
            )
            migrated_count = (await cursor.fetchone())[0]

            if legacy_count > 0 and migrated_count == 0:
                logger.info(
                    "Migrating %d legacy ip_group_items → ip_addresses...",
                    legacy_count,
                )
                await db.execute("""
                    INSERT OR IGNORE INTO ip_addresses (ip_cidr, tag, source, created_at, updated_at)
                    SELECT
                        gi.ip_cidr,
                        g.name,
                        'migrated',
                        gi.created_at,
                        datetime('now')
                    FROM ip_group_items gi
                    JOIN ip_groups g ON gi.group_id = g.id
                """)
                logger.info("Legacy IP group data migration complete.")
        except Exception:
            # ip_group_items or ip_groups may not exist yet on a fresh DB
            pass

        await db.commit()


def _get_db():
    """Get a database connection (caller must use as async context manager)."""
    return aiosqlite.connect(get_db_path())


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
    country: str = "",
    country_code: str = "",
    tags: str = "",
) -> int:
    async with _get_db() as db:
        await db.execute("PRAGMA foreign_keys=ON")
        cursor = await db.execute(
            """INSERT INTO nodes (name, host, ssh_port, ssh_user, snell_port, snell_conf, remark, country, country_code, tags)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, host, ssh_port, ssh_user, snell_port, snell_conf, remark, country, country_code, tags),
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
# IP Addresses (unified IP management — replaces legacy ip_groups)
# ---------------------------------------------------------------------------

async def get_all_ip_addresses() -> list[dict]:
    """Return all registered IP addresses ordered by tag then IP."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ip_addresses ORDER BY tag, ip_cidr"
        )
        return [dict(row) for row in await cursor.fetchall()]


async def get_ip_remarks_map() -> dict[str, str]:
    """Return {ip_cidr: tag} dict for quick lookup during template rendering."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT ip_cidr, tag FROM ip_addresses WHERE tag != ''"
        )
        return {row[0]: row[1] for row in await cursor.fetchall()}


async def get_all_tags() -> list[str]:
    """Return deduplicated list of all non-empty tags."""
    async with _get_db() as db:
        cursor = await db.execute(
            "SELECT DISTINCT tag FROM ip_addresses WHERE tag != '' ORDER BY tag"
        )
        return [row[0] for row in await cursor.fetchall()]


async def get_ips_by_tag(tag: str) -> list[dict]:
    """Return all IP addresses that share the given tag."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM ip_addresses WHERE tag = ? ORDER BY ip_cidr",
            (tag,),
        )
        return [dict(row) for row in await cursor.fetchall()]


async def upsert_ip_address(ip_cidr: str, tag: str = "", source: str = "manual") -> int:
    """Insert a new IP or update existing IP's tag. Returns the row id."""
    async with _get_db() as db:
        cursor = await db.execute(
            """INSERT INTO ip_addresses (ip_cidr, tag, source, updated_at)
               VALUES (?, ?, ?, datetime('now'))
               ON CONFLICT(ip_cidr) DO UPDATE SET
                   tag = CASE WHEN excluded.tag != '' THEN excluded.tag ELSE ip_addresses.tag END,
                   updated_at = datetime('now')""",
            (ip_cidr, tag, source),
        )
        await db.commit()
        return cursor.lastrowid


async def update_ip_address(ip_id: int, **kwargs) -> None:
    """Update an IP address record (e.g. tag, source)."""
    if not kwargs:
        return
    kwargs["updated_at"] = "datetime('now')"
    async with _get_db() as db:
        parts = []
        values = []
        for k, v in kwargs.items():
            if v == "datetime('now')":
                parts.append(f"{k} = datetime('now')")
            else:
                parts.append(f"{k} = ?")
                values.append(v)
        values.append(ip_id)
        await db.execute(
            f"UPDATE ip_addresses SET {', '.join(parts)} WHERE id = ?",
            values,
        )
        await db.commit()


async def delete_ip_address(ip_id: int) -> None:
    """Delete an IP address record by id."""
    async with _get_db() as db:
        await db.execute("DELETE FROM ip_addresses WHERE id = ?", (ip_id,))
        await db.commit()


async def search_ip_addresses(query: str) -> list[dict]:
    """Fuzzy search IP addresses by ip_cidr or tag."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        pattern = f"%{query}%"
        cursor = await db.execute(
            "SELECT * FROM ip_addresses WHERE ip_cidr LIKE ? OR tag LIKE ? ORDER BY tag, ip_cidr",
            (pattern, pattern),
        )
        return [dict(row) for row in await cursor.fetchall()]


# ---------------------------------------------------------------------------
# Legacy IP Groups (kept for backward compatibility during migration)
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


async def get_cached_ip_geo(ip: str) -> dict | None:
    """Get IP geo information from local cache database."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT country, country_code, city, asn FROM ip_geo_cache WHERE ip = ?",
            (ip,),
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
    return None


async def cache_ip_geo(ip: str, country: str, country_code: str, city: str, asn: str):
    """Store IP geo information in the local cache database."""
    async with _get_db() as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO ip_geo_cache (ip, country, country_code, city, asn, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
            """,
            (ip, country, country_code, city, asn),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# Policies & Node Policies
# ---------------------------------------------------------------------------

async def get_node_policies(node_id: int) -> list[dict]:
    """Get all policy records associated with a given node."""
    async with _get_db() as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT p.*, np.enabled as node_enabled, np.last_applied_at, np.last_apply_status, np.last_error
               FROM policies p
               JOIN node_policies np ON p.id = np.policy_id
               WHERE np.node_id = ?""",
            (node_id,)
        )
        return [dict(row) for row in await cursor.fetchall()]

async def create_policy(name: str, service: str, port: int, protocol: str, allow_sets: str, default_action: str = 'drop', enabled: int = 1) -> int:
    async with _get_db() as db:
        cursor = await db.execute(
            """INSERT INTO policies (name, service, port, protocol, allow_sets, default_action, enabled)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, service, port, protocol, allow_sets, default_action, enabled)
        )
        await db.commit()
        return cursor.lastrowid

async def link_node_policy(node_id: int, policy_id: int) -> None:
    async with _get_db() as db:
        await db.execute(
            """INSERT OR IGNORE INTO node_policies (node_id, policy_id, enabled)
               VALUES (?, ?, 1)""",
            (node_id, policy_id)
        )
        await db.commit()

async def update_node_policy_status(node_id: int, policy_id: int, status: str, error_msg: str = "") -> None:
    async with _get_db() as db:
        await db.execute(
            """UPDATE node_policies
               SET last_applied_at = datetime('now'), last_apply_status = ?, last_error = ?
               WHERE node_id = ? AND policy_id = ?""",
            (status, error_msg, node_id, policy_id)
        )
        await db.commit()

async def batch_reset_cn_ips(cidr_list: list[str]) -> None:
    """Clear all records with tag 'cn_ips' and insert the new list inside a transaction."""
    async with _get_db() as db:
        # Delete old
        await db.execute("DELETE FROM ip_addresses WHERE tag = 'cn_ips'")
        
        # Batch Insert
        params = [(cidr, "cn_ips", "cn_zone") for cidr in cidr_list]
        await db.executemany(
            """INSERT INTO ip_addresses (ip_cidr, tag, source)
               VALUES (?, ?, ?)""",
            params
        )
        await db.commit()
