from httpx import AsyncClient
from sqlalchemy import select

from app.models import Subject
from tests.conftest import AuthorizedSession, AuthorizedSessionFactory, TestSessionFactory


async def test_subject_endpoints_require_authentication(client: AsyncClient) -> None:
    subject_id = "00000000-0000-0000-0000-000000000001"

    assert (await client.get("/api/subjects")).status_code == 401
    assert (await client.post("/api/subjects", json={"name": "Physics"})).status_code == 401
    assert (await client.delete(f"/api/subjects/{subject_id}")).status_code == 401


async def test_create_and_list_subjects_for_current_user(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    other = await authorized_session_factory("other@example.com", "other-session")
    async with test_session_factory() as db:
        db.add(Subject(user_id=other.user.id, name="Private subject"))
        await db.commit()

    first = await client.post(
        "/api/subjects",
        json={"name": "Physics"},
        headers=authorized_session.headers,
    )
    second = await client.post(
        "/api/subjects",
        json={"name": "Mathematics"},
        headers=authorized_session.headers,
    )

    assert first.status_code == second.status_code == 201
    assert first.json()["name"] == "Physics"
    assert second.json()["name"] == "Mathematics"
    listed = await client.get(
        "/api/subjects",
        headers=authorized_session.headers,
    )
    assert listed.status_code == 200
    assert [subject["name"] for subject in listed.json()] == ["Physics", "Mathematics"]

    async with test_session_factory() as db:
        stored = list(
            await db.scalars(select(Subject).where(Subject.user_id == authorized_session.user.id))
        )
    assert [subject.name for subject in stored] == ["Physics", "Mathematics"]


async def test_delete_subject_is_scoped_to_current_user(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    other = await authorized_session_factory("other@example.com", "other-session")
    async with test_session_factory() as db:
        subject = Subject(user_id=authorized_session.user.id, name="Physics")
        db.add(subject)
        await db.commit()
        subject_id = subject.id

    foreign_delete = await client.delete(
        f"/api/subjects/{subject_id}",
        headers=other.headers,
    )
    assert foreign_delete.status_code == 404

    owner_delete = await client.delete(
        f"/api/subjects/{subject_id}",
        headers=authorized_session.headers,
    )
    assert owner_delete.status_code == 204
    assert owner_delete.content == b""

    repeated_delete = await client.delete(
        f"/api/subjects/{subject_id}",
        headers=authorized_session.headers,
    )
    assert repeated_delete.status_code == 404

    async with test_session_factory() as db:
        assert await db.get(Subject, subject_id) is None
