from uuid import UUID, uuid4

from httpx import AsyncClient
from icalendar import Calendar
from icalendar.cal import Event

from app.models import Deadline, DocumentFile, Subject
from tests.conftest import AuthorizedSession, AuthorizedSessionFactory, TestSessionFactory


async def create_deadline(
    test_session_factory: TestSessionFactory,
    user_id: UUID,
    *,
    subject_name: str,
    title: str,
    due_date: str | None,
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
            date_note=None,
            requirements=["Submit report"],
            source_page=1,
            source_quote="Submit before the deadline",
            status="confirmed",
        )
        db.add(deadline)
        await db.commit()
        return deadline


def calendar_events(content: bytes) -> list[Event]:
    components = Calendar.from_ical(content).walk("VEVENT")
    assert all(isinstance(component, Event) for component in components)
    return [component for component in components if isinstance(component, Event)]


async def test_calendar_export_requires_authentication(client: AsyncClient) -> None:
    response = await client.get("/api/calendar.ics")

    assert response.status_code == 401


async def test_calendar_export_returns_owned_dated_deadlines(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Databases",
        title="Database project",
        due_date="2026-11-10",
    )
    await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Algorithms",
        title="Undated exercise",
        due_date=None,
    )
    other = await authorized_session_factory("other@example.com", "other-session")
    await create_deadline(
        test_session_factory,
        other.user.id,
        subject_name="Private",
        title="Private deadline",
        due_date="2026-12-01",
    )

    response = await client.get("/api/calendar.ics", headers=authorized_session.headers)

    assert response.status_code == 200
    assert response.headers["content-type"] == "text/calendar; charset=utf-8"
    assert response.headers["content-disposition"] == (
        'attachment; filename="studyhub-deadlines.ics"'
    )
    events = calendar_events(response.content)
    assert [str(event.get("summary")) for event in events] == ["Database project"]


async def test_calendar_export_filters_by_owned_subject_without_disclosure(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    selected = await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Databases",
        title="Database project",
        due_date="2026-11-10",
    )
    await create_deadline(
        test_session_factory,
        authorized_session.user.id,
        subject_name="Algorithms",
        title="Algorithm project",
        due_date="2026-11-20",
    )
    other = await authorized_session_factory("other@example.com", "other-session")
    foreign = await create_deadline(
        test_session_factory,
        other.user.id,
        subject_name="Private",
        title="Private deadline",
        due_date="2026-12-01",
    )

    selected_response = await client.get(
        "/api/calendar.ics",
        params={"subject_id": str(selected.subject_id)},
        headers=authorized_session.headers,
    )
    foreign_response = await client.get(
        "/api/calendar.ics",
        params={"subject_id": str(foreign.subject_id)},
        headers=authorized_session.headers,
    )

    assert selected_response.status_code == 200
    assert [str(event.get("summary")) for event in calendar_events(selected_response.content)] == [
        "Database project"
    ]
    assert foreign_response.status_code == 200
    assert calendar_events(foreign_response.content) == []
