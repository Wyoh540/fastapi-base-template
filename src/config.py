"""Application-wide settings.

Domain-scoped settings live next to their domain (``src/auth/config.py``).
This module only owns concerns that are genuinely global: runtime environment,
database wiring and CORS.
"""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Versioned mount point for every router.
API_PREFIX = "/api/v1"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # -- Application ----------------------------------------------------
    ENVIRONMENT: str = "local"
    DEBUG: bool = False

    # -- Database --------------------------------------------------------
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"
    DATABASE_ECHO: bool = False
    # Off by default: Alembic is the single source of truth for the schema.
    # Enabling `create_all` makes migrations fail with "table already exists".
    AUTO_CREATE_TABLES: bool = False

    # -- Pagination ------------------------------------------------------
    DEFAULT_PAGE_SIZE: int = 20
    MAX_PAGE_SIZE: int = 100

    # -- CORS ------------------------------------------------------------
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        """Accept a comma-separated string for env-var friendliness."""
        if isinstance(value, str) and not value.strip().startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def is_local(self) -> bool:
        return self.ENVIRONMENT.lower() in {"local", "dev", "development"}


@lru_cache
def get_settings() -> Settings:
    """Cached settings singleton (``lru_cache`` keeps env reads to one pass)."""
    return Settings()


settings = get_settings()
