from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
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


def init_db() -> None:
    database_url = str(engine.url)
    if database_url.startswith("sqlite:///"):
        db_path = database_url.removeprefix("sqlite:///")
        from pathlib import Path

        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
