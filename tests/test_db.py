import os

from pydantic import SecretStr
from sqlalchemy.orm import configure_mappers

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USERNAME", "studyhub")
os.environ.setdefault("DB_PASSWORD", "studyhub")
os.environ.setdefault("DB_NAME", "studyhub")

from app import models  # noqa: F401
from app.config import Settings
from app.db import Base, engine


def test_default_database_driver_is_asyncpg() -> None:
    settings = Settings(
        database_host="db.internal",
        database_port=5433,
        database_username="api-user",
        database_password=SecretStr("p@ss/word"),
        database_name="studyhub-test",
    )

    assert settings.database_url.drivername == "postgresql+asyncpg"
    assert settings.database_url.host == "db.internal"
    assert settings.database_url.port == 5433
    assert settings.database_url.username == "api-user"
    assert settings.database_url.password == "p@ss/word"
    assert settings.database_url.database == "studyhub-test"
    assert engine.dialect.driver == "asyncpg"


def test_all_relationships_forbid_implicit_queries() -> None:
    configure_mappers()

    relationships = [
        relationship for mapper in Base.registry.mappers for relationship in mapper.relationships
    ]

    assert relationships
    assert all(relationship.lazy == "raise" for relationship in relationships)
