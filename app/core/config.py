import os
from typing import Any, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    PROJECT_NAME: str = "Subscription Manager"
    VERSION: str = "0.1.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    @field_validator("DEBUG", mode="before")
    @classmethod
    def parse_debug(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            val = v.strip().lower()
            if val in ("false", "0", "no", "off", "release", "prod", "production"):
                return False
            if val in ("true", "1", "yes", "on", "debug", "dev", "development"):
                return True
        return False

    # Security & JWT
    SECRET_KEY: str = "insecure_dev_secret_key_change_in_production_min_32_bytes_long"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 30

    # Cookie settings
    COOKIE_NAME: str = "access_token"
    COOKIE_SECURE: bool = False
    COOKIE_SAMESITE: str = "lax"
    COOKIE_HTTPONLY: bool = True

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/subscription_manager"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # Reference Organization Seed
    INITIAL_TENANT_NAME: str = "Brightloop Software"
    INITIAL_TENANT_SLUG: str = "brightloop-software"

    # Reference Admin Seed
    FIRST_ADMIN_EMAIL: str = "admin@brightloop.io"
    FIRST_ADMIN_PASSWORD: str = "Admin@Brightloop123"
    FIRST_ADMIN_NAME: str = "Brightloop Admin"

    # Development simulation
    ENABLE_DEV_PASSWORD_RESET_SIMULATION: bool = True

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def resolved_cookie_secure(self) -> bool:
        return True if self.is_production else self.COOKIE_SECURE


settings = Settings()
