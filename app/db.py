from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def make_engine(database_url: str) -> Engine:
    return create_engine(
        database_url,
        connect_args={"check_same_thread": False}
        if database_url.startswith("sqlite")
        else {},
    )


settings = get_settings()
engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def configure_database(database_url: str) -> None:
    global engine, SessionLocal
    engine = make_engine(database_url)
    SessionLocal.configure(bind=engine)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _sqlite_column_type(target_engine: Engine, column) -> str:
    return column.type.compile(dialect=target_engine.dialect)


def _sqlite_column_definition(target_engine: Engine, column) -> str:
    definition = f"{column.name} {_sqlite_column_type(target_engine, column)}"
    if not column.nullable and column.default is not None:
        default_arg = column.default.arg
        if isinstance(default_arg, bool):
            definition += f" DEFAULT {1 if default_arg else 0}"
        elif isinstance(default_arg, (int, float)):
            definition += f" DEFAULT {default_arg}"
        elif isinstance(default_arg, str):
            definition += f" DEFAULT '{default_arg}'"
    if not column.nullable:
        definition += " NOT NULL"
    return definition


def run_sqlite_migrations(target_engine: Engine) -> None:
    inspector = inspect(target_engine)
    existing_tables = set(inspector.get_table_names())
    with target_engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL
                )
                """
            )
        )
        existing_tables.add("schema_migrations")
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            existing_columns = {column["name"] for column in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns or column.primary_key:
                    continue
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {_sqlite_column_definition(target_engine, column)}"))
        conn.execute(text("INSERT OR IGNORE INTO schema_migrations (version) VALUES (1)"))


def init_db() -> None:
    database_url = str(engine.url)
    if database_url.startswith("sqlite:///"):
        db_path = database_url.removeprefix("sqlite:///")
        from pathlib import Path

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    if database_url.startswith("sqlite"):
        run_sqlite_migrations(engine)
