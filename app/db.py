from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import relationship as sqlalchemy_relationship
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def relationship(*args: Any, **kwargs: Any) -> Any:
    """Declare an ORM relationship that forbids implicit database queries."""
    kwargs.setdefault("lazy", "raise")
    return sqlalchemy_relationship(*args, **kwargs)


database_url = get_settings().database_url
engine_options: dict[str, object] = {"pool_pre_ping": True}
if database_url.drivername.startswith("sqlite"):
    engine_options.update(poolclass=StaticPool)
engine = create_async_engine(database_url, **engine_options)
SessionLocal = async_sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
