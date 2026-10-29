from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Environment & Logging
    APP_ENV: Literal["development", "test", "production"] = "development"
    LOG_LEVEL: str = "INFO"
    SECRET_KEY: str = Field(
        default="development_secret_key_at_least_32_characters_long_min_len",
        min_length=32,
    )

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inzar"
    DATABASE_URL_DIRECT: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inzar"
    TEST_DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/inzar_test"
    DATABASE_SSL: bool = False

    # Authentication & Tokens
    ACCESS_TOKEN_TTL_MINUTES: int = 15
    REFRESH_TOKEN_TTL_DAYS: int = 30
    EMAIL_TOKEN_TTL_HOURS: int = 24
    GOOGLE_CLIENT_IDS: list[str] | str = Field(default_factory=list)

    # CORS
    CORS_ORIGINS: list[str] | str = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str = "demo"
    CLOUDINARY_API_KEY: str = "123456789012345"
    CLOUDINARY_API_SECRET: str = "abcdefghijklmnopqrstuvwxyz12"
    CLOUDINARY_UPLOAD_FOLDER: str = "inzar/incidents"

    # Email
    EMAIL_PROVIDER: Literal["console", "resend"] = "console"
    RESEND_API_KEY: str = ""
    EMAIL_FROM: str = "Inzar Alerts <alerts@inzar.app>"

    # Push Notifications
    PUSH_PROVIDER: Literal["log", "fcm"] = "log"
    FCM_PROJECT_ID: str = "inzar-app"
    FCM_SERVICE_ACCOUNT_JSON: str = ""

    # Review Pipeline
    REVIEW_PROVIDER: Literal["stub"] = "stub"

    # Rate Limiting
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    RATE_LIMIT_SUBMISSION_PER_HOUR: int = 30
    RATE_LIMIT_SIGNING_PER_MINUTE: int = 15
    RATE_LIMIT_FLAG_PER_MINUTE: int = 20

    # Optional Monitoring
    SENTRY_DSN: str | None = None

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        if isinstance(v, list):
            return [str(origin).strip() for origin in v if str(origin).strip()]
        return ["*"]

    @field_validator("GOOGLE_CLIENT_IDS", mode="before")
    @classmethod
    def parse_google_client_ids(cls, v: object) -> list[str]:
        if isinstance(v, str):
            return [client_id.strip() for client_id in v.split(",") if client_id.strip()]
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return []


settings = Settings()
