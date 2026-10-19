from functools import lru_cache
from pathlib import Path
from typing import Self

from pydantic import EmailStr, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        validate_by_name=True,
    )

    database_host: str = Field(validation_alias="DB_HOST")
    database_port: int = Field(validation_alias="DB_PORT", ge=1, le=65535)
    database_username: str = Field(validation_alias="DB_USERNAME")
    database_password: SecretStr = Field(validation_alias="DB_PASSWORD")
    database_name: str = Field(validation_alias="DB_NAME")
    session_ttl_seconds: int = Field(
        default=60 * 60 * 24 * 30,
        validation_alias="SESSION_TTL_SECONDS",
        gt=0,
    )
    verification_token_ttl_seconds: int = Field(
        default=60 * 60 * 24,
        validation_alias="VERIFICATION_TOKEN_TTL_SECONDS",
        gt=0,
    )
    cookie_secure: bool = Field(default=False, validation_alias="COOKIE_SECURE")
    emails_enabled: bool = Field(default=True, validation_alias="EMAILS_ENABLED")
    smtp_host: str = Field(default="localhost", validation_alias="SMTP_HOST")
    smtp_port: int = Field(default=1025, validation_alias="SMTP_PORT", ge=1, le=65535)
    smtp_username: str | None = Field(default=None, validation_alias="SMTP_USERNAME")
    smtp_password: SecretStr | None = Field(default=None, validation_alias="SMTP_PASSWORD")
    smtp_from_email: EmailStr = Field(
        default="noreply@studyhub.example.com", validation_alias="SMTP_FROM_EMAIL"
    )
    smtp_start_tls: bool = Field(default=True, validation_alias="SMTP_START_TLS")
    smtp_use_tls: bool = Field(default=False, validation_alias="SMTP_USE_TLS")
    smtp_timeout_seconds: float = Field(
        default=10.0,
        validation_alias="SMTP_TIMEOUT_SECONDS",
        gt=0,
    )
    storage_path: Path = Field(default=Path("uploads"), validation_alias="STORAGE_PATH")

    @field_validator("smtp_username", "smtp_password", mode="before")
    @classmethod
    def empty_smtp_credentials_are_absent(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_smtp_tls_modes(self) -> Self:
        if self.smtp_start_tls and self.smtp_use_tls:
            raise ValueError("SMTP_START_TLS and SMTP_USE_TLS cannot both be enabled")
        return self

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.database_username,
            password=self.database_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.database_name,
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
