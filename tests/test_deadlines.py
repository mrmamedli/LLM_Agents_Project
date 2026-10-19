from uuid import UUID, uuid4

from httpx import AsyncClient

from app.models import Deadline, DocumentFile, Subject
from tests.conftest import AuthorizedSession, AuthorizedSessionFactory, TestSessionFactory


async def create_deadline(
    test_session_factory: TestSessionFactory,
    user_id: UUID,
    *,
    subject_name: str,
    title: str,
    due_date: str | None = None,
) -> Deadline:
    async with test_session_factory() as db:
        subject = Subject(user_id=user_id, name=subject_name)
        db.add(subject)
        await db.flush()
        document = DocumentFile(
            subject_id=subject.id,
            filename=f"{title}.pdf",
            storage_key=f"{uuid4()}.pdf",
        )
        db.add(document)
        await db.flush()
        deadline = Deadline(
            file_id=document.id,
            subject_id=subject.id,
            title=title,
            due_date=due_date,
            date_note="Original wording",
            requirements=["Submit report"],
            source_page=2,
            source_quote="Submit before the deadline",
            status="needs_confirmation",
        )
        deadline.related_files.append(document)
        db.add(deadline)
        await db.commit()
        return deadline


async def test_deadline_endpoints_require_authentication(client: AsyncClient) -> None:
    deadline_id = "00000000-0000-0000-0000-000000000001"

    assert (await client.get("/api/deadlines")).status_code == 401
    update = await client.patch(
        f"/api/deadlines/{deadline_id}",
        json={"due_date": "2026-11-10", "status": "confirmed"},
    )
    assert update.status_code == 401


async def test_list_deadlines_is_user_scoped_and_includes_related_files(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    first = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Databases",
        title="Database project",
        due_date="2026-11-10",
    )
    second = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Algorithms",
        title="Algorithm project",
    )
    other = await authorized_session_factory("other@example.com", "other-session")
    foreign = await create_deadline(
        test_session_factory,
        other.user.id,
        subject_name="Private",
        title="Private deadline",
    )

    response = await client.get("/api/deadlines", headers=authorized_session.headers)
    selected = await client.get(
        "/api/deadlines",
        params={"subject_id": str(first.subject_id)},
        headers=authorized_session.headers,
    )
    foreign_filter = await client.get(
        "/api/deadlines",
        params={"subject_id": str(foreign.subject_id)},
        headers=authorized_session.headers,
    )

    assert response.status_code == 200
    payload_by_id = {item["id"]: item for item in response.json()}
    assert set(payload_by_id) == {str(first.id), str(second.id)}
    assert payload_by_id[str(first.id)]["related_files"][0]["id"] == str(first.file_id)
    assert selected.status_code == 200
    assert [item["id"] for item in selected.json()] == [str(first.id)]
    assert foreign_filter.status_code == 200
    assert foreign_filter.json() == []


async def test_update_deadline_changes_owned_fields_and_hides_foreign_deadline(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    deadline = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Databases",
        title="Database project",
    )
    other = await authorized_session_factory("other@example.com", "other-session")

    foreign_update = await client.patch(
        f"/api/deadlines/{deadline.id}",
        json={"due_date": "2026-11-10", "status": "confirmed"},
        headers=other.headers,
    )
    update = await client.patch(
        f"/api/deadlines/{deadline.id}",
        json={"due_date": "2026-11-10T18:30:00+03:00", "status": "confirmed"},
        headers=authorized_session.headers,
    )

    assert foreign_update.status_code == 404
    assert update.status_code == 200
    payload = update.json()
    assert payload["due_date"] == "2026-11-10T18:30:00+03:00"
    assert payload["status"] == "confirmed"
    assert payload["date_note"] == "Original wording"
    assert payload["related_files"][0]["id"] == str(deadline.file_id)

    async with test_session_factory() as db:
        stored = await db.get(Deadline, deadline.id)
        assert stored is not None
        assert stored.due_date == "2026-11-10T18:30:00+03:00"
        assert stored.status == "confirmed"
