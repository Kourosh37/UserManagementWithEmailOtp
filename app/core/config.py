from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    PROJECT_NAME: str = "Auth Service"
    PROJECT_VERSION: str = "1.0.0"

    DATABASE_URL: str = Field(..., description="PostgreSQL URL using asyncpg, e.g. postgresql+asyncpg://user:pass@host:5432/db")
    REDIS_URL: str = Field("redis://localhost:6379/0", description="Redis URL for OTP storage")

    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    OTP_EXPIRE_SECONDS: int = 120
    OTP_LENGTH: int = 6

    SMTP_SERVER: str | None = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: str | None = None
    SMTP_PASSWORD: str | None = None
    FROM_EMAIL: str | None = None

    ALLOWED_ORIGINS: List[str] = [
        "http://127.0.0.1:5500",
        "http://localhost:5500",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
