from __future__ import annotations

from sqlalchemy import create_engine, inspect, text

import app.models  # noqa: F401
from app.db import Base, run_sqlite_migrations


def test_sqlite_migrations_add_missing_columns_and_schema_version() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE nodes (
                    id INTEGER PRIMARY KEY,
                    name VARCHAR(120) NOT NULL,
                    host VARCHAR(255),
                    ssh_port INTEGER,
                    ssh_user VARCHAR(64),
                    snell_port INTEGER NOT NULL
                )
                """
            )
        )
    Base.metadata.create_all(bind=engine)

    run_sqlite_migrations(engine)

    inspector = inspect(engine)
    node_columns = {column["name"] for column in inspector.get_columns("nodes")}
    assert "ssh_alias" in node_columns
    assert "connect_timeout" in node_columns
    assert "enable_udp" in node_columns
    assert "last_error" in node_columns
    assert "schema_migrations" in inspector.get_table_names()


def test_sqlite_migrations_are_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)

    run_sqlite_migrations(engine)
    run_sqlite_migrations(engine)

    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version FROM schema_migrations")).all()
    assert rows == [(1,)]
