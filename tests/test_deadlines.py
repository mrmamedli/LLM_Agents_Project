from uuid import UUID, uuid4

from httpx import AsyncClient
from sqlalchemy import select

from app.models import Deadline, DocumentFile, Subject, deadline_related_files
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
    create = await client.post(
        "/api/deadlines",
        json={"subject_id": deadline_id, "title": "Manual", "due_date": "2026-11-10"},
    )
    assert create.status_code == 401
    delete_response = await client.delete(f"/api/deadlines/{deadline_id}")
    assert delete_response.status_code == 401


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


async def create_subject_with_file(
    test_session_factory: TestSessionFactory,
    user_id: UUID,
    name: str = "Databases",
) -> tuple[Subject, DocumentFile]:
    async with test_session_factory() as db:
        subject = Subject(user_id=user_id, name=name)
        db.add(subject)
        await db.flush()
        document = DocumentFile(
            subject_id=subject.id,
            filename="syllabus.pdf",
            storage_key=f"{uuid4()}.pdf",
            status="done",
        )
        db.add(document)
        await db.commit()
        return subject, document


async def test_create_manual_deadline_without_file(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
) -> None:
    subject, _ = await create_subject_with_file(test_session_factory, authorized_session.user.id)

    response = await client.post(
        "/api/deadlines",
        json={
            "subject_id": str(subject.id),
            "title": "  Lab report  ",
            "due_date": "2026-11-12T18:00",
            "requirements": ["PDF", "Max 5 pages"],
        },
        headers=authorized_session.headers,
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Lab report"
    assert payload["subject_id"] == str(subject.id)
    assert payload["file_id"] is None
    assert payload["due_date"] == "2026-11-12T18:00"
    assert payload["date_note"] is None
    assert payload["requirements"] == ["PDF", "Max 5 pages"]
    assert payload["source_page"] is None
    assert payload["source_quote"] is None
    assert payload["status"] == "confirmed"
    assert payload["is_manual"] is True
    assert payload["related_files"] == []

    listed = await client.get("/api/deadlines", headers=authorized_session.headers)
    assert [item["id"] for item in listed.json()] == [payload["id"]]
    calendar = await client.get("/api/calendar.ics", headers=authorized_session.headers)
    assert b"SUMMARY:Lab report" in calendar.content


async def test_create_manual_deadline_without_date_is_undefined(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
) -> None:
    subject, _ = await create_subject_with_file(test_session_factory, authorized_session.user.id)

    response = await client.post(
        "/api/deadlines",
        json={"subject_id": str(subject.id), "title": "Find out the date"},
        headers=authorized_session.headers,
    )

    assert response.status_code == 201
    assert response.json()["due_date"] is None
    assert response.json()["status"] == "undefined"
    assert response.json()["requirements"] == []


async def test_create_manual_deadline_linked_to_file_shows_in_file_card(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
) -> None:
    subject, document = await create_subject_with_file(
        test_session_factory, authorized_session.user.id
    )

    created = await client.post(
        "/api/deadlines",
        json={
            "subject_id": str(subject.id),
            "file_id": str(document.id),
            "title": "Project defence",
            "due_date": "2026-12-01",
        },
        headers=authorized_session.headers,
    )
    card = await client.get(f"/api/files/{document.id}", headers=authorized_session.headers)

    assert created.status_code == 201
    assert created.json()["file_id"] == str(document.id)
    assert [item["id"] for item in card.json()["deadlines"]] == [created.json()["id"]]


async def test_create_manual_deadline_validates_input(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
) -> None:
    subject, _ = await create_subject_with_file(test_session_factory, authorized_session.user.id)
    base = {"subject_id": str(subject.id), "title": "Homework", "due_date": "2026-11-10"}

    for override in (
        {"title": "   "},
        {"title": "x" * 513},
        {"due_date": "next friday"},
        {"due_date": ""},
        {"due_date": "2026-13-40"},
        {"requirements": "not a list"},
        {"requirements": ["PDF", "  "]},
    ):
        response = await client.post(
            "/api/deadlines",
            json={**base, **override},
            headers=authorized_session.headers,
        )
        assert response.status_code == 422, override


async def test_create_manual_deadline_hides_foreign_subject_and_file(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    own_subject, _ = await create_subject_with_file(
        test_session_factory, authorized_session.user.id, "Own"
    )
    other = await authorized_session_factory("other@example.com", "other-session")
    foreign_subject, foreign_file = await create_subject_with_file(
        test_session_factory, other.user.id, "Foreign"
    )

    foreign_subject_response = await client.post(
        "/api/deadlines",
        json={"subject_id": str(foreign_subject.id), "title": "Nope"},
        headers=authorized_session.headers,
    )
    foreign_file_response = await client.post(
        "/api/deadlines",
        json={
            "subject_id": str(own_subject.id),
            "file_id": str(foreign_file.id),
            "title": "Nope",
        },
        headers=authorized_session.headers,
    )

    assert foreign_subject_response.status_code == 404
    assert foreign_file_response.status_code == 404
    async with test_session_factory() as db:
        assert list(await db.scalars(select(Deadline))) == []


async def test_delete_deadline_removes_it_with_related_files_link(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
) -> None:
    deleted = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Databases",
        title="Extra deadline",
    )
    kept = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Algorithms",
        title="Real deadline",
    )

    response = await client.delete(
        f"/api/deadlines/{deleted.id}", headers=authorized_session.headers
    )
    listed = await client.get("/api/deadlines", headers=authorized_session.headers)
    repeated = await client.delete(
        f"/api/deadlines/{deleted.id}", headers=authorized_session.headers
    )

    assert response.status_code == 204
    assert response.content == b""
    assert [item["id"] for item in listed.json()] == [str(kept.id)]
    assert repeated.status_code == 404
    async with test_session_factory() as db:
        links = list(await db.execute(select(deadline_related_files.c.deadline_id)))
        assert [row.deadline_id for row in links] == [kept.id]


async def test_delete_deadline_hides_foreign_deadline(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    other = await authorized_session_factory("other@example.com", "other-session")
    foreign = await create_deadline(
        test_session_factory,
        other.user.id,
        subject_name="Private",
        title="Private deadline",
    )

    response = await client.delete(
        f"/api/deadlines/{foreign.id}", headers=authorized_session.headers
    )

    assert response.status_code == 404
    async with test_session_factory() as db:
        assert await db.get(Deadline, foreign.id) is not None
