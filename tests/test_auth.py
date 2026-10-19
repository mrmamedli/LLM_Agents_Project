import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
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

from app.config import Settings
from app.db import Base, get_db
from app.main import app
from app.models import User, UserSession
from app.security import hash_password, verify_password

test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    poolclass=StaticPool,
)
TestSession = async_sessionmaker(test_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def sent_verification_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[str, str]]:
    sent: list[tuple[str, str]] = []

    async def record_email(recipient: str, token: str, settings: Settings) -> None:
        del settings
        sent.append((recipient, token))

    monkeypatch.setattr("app.routers.auth.send_verification_email", record_email)
    return sent


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestSession() as session:
        yield session


@pytest.fixture(autouse=True)
async def database() -> AsyncGenerator[None, None]:
    app.dependency_overrides[get_db] = override_get_db
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield
    app.dependency_overrides.clear()
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


async def get_user(email: str) -> User | None:
    async with TestSession() as db:
        return await db.scalar(select(User).where(User.email == email))


async def register(client: AsyncClient, email: str = "student@example.com") -> User:
    response = await client.post(
        "/api/auth/register",
        json={"email": email, "password": "password123"},
    )
    assert response.status_code == 201
    user = await get_user(email.lower())
    assert user is not None
    return user


async def verify_registered_user(client: AsyncClient, user: User) -> None:
    assert user.verification_token is not None
    response = await client.post(
        "/api/auth/verify-email",
        json={"token": user.verification_token},
    )
    assert response.status_code == 204


async def test_register_hashes_password_and_rejects_duplicate_email(
    client: AsyncClient,
    sent_verification_emails: list[tuple[str, str]],
) -> None:
    user = await register(client, "Student@Example.COM")

    assert user.email == "student@example.com"
    assert user.password_hash != "password123"
    assert verify_password("password123", user.password_hash)
    assert user.verification_token is not None
    assert user.verification_token_expires_at is not None
    assert sent_verification_emails == [(user.email, user.verification_token)]

    duplicate = await client.post(
        "/api/auth/register",
        json={"email": "student@example.com", "password": "password123"},
    )
    assert duplicate.status_code == 409
    assert sent_verification_emails == [(user.email, user.verification_token)]


async def test_login_requires_valid_credentials_and_verified_email(client: AsyncClient) -> None:
    user = await register(client)

    wrong_password = await client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )
    assert wrong_password.status_code == 401

    unverified = await client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    assert unverified.status_code == 403


async def test_verify_email_rejects_expired_token(client: AsyncClient) -> None:
    user = await register(client)
    assert user.verification_token is not None
    token = user.verification_token
    async with TestSession() as db:
        stored_user = await db.get(User, user.id)
        assert stored_user is not None
        stored_user.verification_token_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await db.commit()

    response = await client.post("/api/auth/verify-email", json={"token": token})
    assert response.status_code == 400


async def test_refresh_rotates_token_without_disclosing_unknown_email(
    client: AsyncClient,
    sent_verification_emails: list[tuple[str, str]],
) -> None:
    user = await register(client)
    old_token = user.verification_token
    assert old_token is not None

    refreshed = await client.post(
        "/api/auth/verification-token/refresh",
        json={"email": user.email},
    )
    unknown = await client.post(
        "/api/auth/verification-token/refresh",
        json={"email": "unknown@example.com"},
    )

    assert refreshed.status_code == unknown.status_code == 202
    updated_user = await get_user(user.email)
    assert updated_user is not None
    assert updated_user.verification_token != old_token
    assert updated_user.verification_token is not None
    assert sent_verification_emails == [
        (user.email, old_token),
        (user.email, updated_user.verification_token),
    ]

    await verify_registered_user(client, updated_user)
    verified = await client.post(
        "/api/auth/verification-token/refresh",
        json={"email": user.email},
    )
    assert verified.status_code == 202
    assert len(sent_verification_emails) == 2


async def test_login_sets_httponly_cookie_and_logout_revokes_session(
    client: AsyncClient,
) -> None:
    user = await register(client)
    await verify_registered_user(client, user)

    login = await client.post(
        "/api/auth/login",
        json={"email": user.email, "password": "password123"},
    )
    assert login.status_code == 204
    assert "HttpOnly" in login.headers["set-cookie"]
    session_id = client.cookies.get("session_id")
    assert session_id is not None

    async with TestSession() as db:
        assert await db.get(UserSession, session_id) is not None

    logout = await client.post("/api/auth/logout")
    assert logout.status_code == 204
    assert "session_id=" in logout.headers["set-cookie"]
    async with TestSession() as db:
        assert await db.get(UserSession, session_id) is None

    assert (await client.post("/api/auth/logout")).status_code == 401


def test_password_verification_rejects_invalid_hashes() -> None:
    password_hash = hash_password("password123")

    assert verify_password("password123", password_hash)
    assert not verify_password("wrong-password", password_hash)
    assert not verify_password("password123", "invalid")
    assert not verify_password("password123", "unknown$00$00")
