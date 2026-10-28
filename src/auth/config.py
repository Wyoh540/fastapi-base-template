"""Authentication domain settings (env prefix ``AUTH_``)."""

from datetime import timedelta

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# RFC 7518 §3.2: HMAC-SHA256 keys must be at least 256 bits (32 bytes) long.
MIN_SECRET_BYTES = 32


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AUTH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    JWT_ALG: str = "HS256"
    JWT_SECRET: str = "dev-insecure-access-secret-change-me"
    JWT_EXP_MINUTES: int = 5

    REFRESH_TOKEN_KEY: str = "dev-insecure-refresh-key-change-me"
    REFRESH_TOKEN_EXP: timedelta = timedelta(days=30)

    SECURE_COOKIES: bool = True

    @field_validator("JWT_SECRET", "REFRESH_TOKEN_KEY")
    @classmethod
    def _secret_min_length(cls, value: str) -> str:
        if len(value.encode("utf-8")) < MIN_SECRET_BYTES:
            raise ValueError(
                f"HMAC secrets must be at least {MIN_SECRET_BYTES} bytes long "
                "(RFC 7518 section 3.2)."
            )
        return value

    @property
    def access_token_expire(self) -> timedelta:
        return timedelta(minutes=self.JWT_EXP_MINUTES)


auth_settings = AuthConfig()
