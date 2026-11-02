"""Permission domain settings (env prefix ``PERMISSION_``)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PermissionConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PERMISSION_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Path to the Casbin model file. Empty means "use the one shipped with the
    # package" (``src/permission/model.conf``).
    MODEL_PATH: str = ""

    # Run the idempotent seed on startup (roles + default policies + admin).
    SEED_ENABLED: bool = True

    # The account that receives the ``admin`` role when seeding.
    SEED_ADMIN_EMAIL: str = "admin@example.com"
    # Leave empty to generate a random password for a newly created admin.
    SEED_ADMIN_PASSWORD: str = ""

    # The role that owns everything. It may not be deleted.
    ADMIN_ROLE: str = "admin"


permission_settings = PermissionConfig()
