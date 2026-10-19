from functools import lru_cache

from pydantic import Field, SecretStr
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
