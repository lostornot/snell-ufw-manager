from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="HOST")
    port: int = Field(default=8898, alias="PORT")
    data_dir: Path = Field(default=Path("data"), alias="DATA_DIR")
    database_url: str = Field(
        default="sqlite:///data/snell-ufw-control.db",
        alias="DATABASE_URL",
    )
    admin_token: str | None = Field(default=None, alias="ADMIN_TOKEN")
    session_secret: str | None = Field(default=None, alias="SESSION_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()

