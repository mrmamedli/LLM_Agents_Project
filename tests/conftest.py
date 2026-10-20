import os
from collections.abc import AsyncGenerator, Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

os.environ.setdefault("DB_HOST", "localhost")
os.environ.setdefault("DB_PORT", "5432")
os.environ.setdefault("DB_USERNAME", "studyhub")
os.environ.setdefault("DB_PASSWORD", "studyhub")
os.environ.setdefault("DB_NAME", "studyhub")
os.environ.setdefault("SMTP_HOST", "smtp.example.com")
os.environ.setdefault("SMTP_PORT", "587")
os.environ.setdefault("SMTP_FROM_EMAIL", "noreply@example.com")

os.environ.setdefault("OPENAI_API_KEY", "studyhub")

from app.config import Settings, get_settings
from app.db import Base, get_db
from app.main import app
from app.models import User, UserSession
from app.security import expires_in

TestSessionFactory = async_sessionmaker[AsyncSession]


@dataclass(frozen=True)
class AuthorizedSession:
    user: User
    token: str
    headers: dict[str, str]


AuthorizedSessionFactory = Callable[[str, str], Awaitable[AuthorizedSession]]

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture
def test_settings(tmp_path: Path) -> Settings:
    return Settings(
        database_host="localhost",
        database_port=5432,
        database_username="studyhub",
        database_password="studyhub",
        database_name="studyhub",
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_from_email="noreply@example.com",
        storage_path=tmp_path / "uploads",
    )


@pytest.fixture
def test_app() -> FastAPI:
    return app


@pytest.fixture
def test_session_factory() -> TestSessionFactory:
    return TestSession


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session


@pytest.fixture
async def database(test_app: FastAPI, test_settings: Settings) -> AsyncGenerator[None, None]:
    def override_get_settings() -> Settings:
        return test_settings

    test_app.dependency_overrides[get_db] = override_get_db
    test_app.dependency_overrides[get_settings] = override_get_settings
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    test_app.dependency_overrides.clear()
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client(test_app: FastAPI, database: None) -> AsyncGenerator[AsyncClient, None]:
    del database
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def authorized_session_factory(
    test_session_factory: TestSessionFactory,
) -> AuthorizedSessionFactory:
    async def create(email: str, token: str) -> AuthorizedSession:
        async with test_session_factory() as db:
            user = User(email=email, password_hash="unused", is_verified=True)
            db.add(user)
            await db.flush()
            db.add(UserSession(id=token, user_id=user.id, expires_at=expires_in(3600)))
            await db.commit()
        return AuthorizedSession(
            user=user,
            token=token,
            headers={"Cookie": f"session_id={token}"},
        )

    return create


@pytest.fixture
async def authorized_session(
    authorized_session_factory: AuthorizedSessionFactory,
) -> AuthorizedSession:
    return await authorized_session_factory("student@example.com", "student-session")
