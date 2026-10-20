from datetime import date
from typing import Any
from uuid import UUID

from icalendar import Calendar
from icalendar.cal import Event

from app.schemas import DeadlineOut
from app.services.ics_export import export_ics


def make_deadline(**overrides: Any) -> DeadlineOut:
    data = {
        "id": UUID("00000000-0000-0000-0000-000000000001"),
        "file_id": UUID("00000000-0000-0000-0000-000000000002"),
        "subject_id": UUID("00000000-0000-0000-0000-000000000003"),
        "title": "Project proposal",
        "due_date": "2026-11-10",
        "date_note": None,
        "requirements": ["Dockerfile", ".env.example"],
        "source_page": 2,
        "source_quote": "Deadlines are announced in the group chat.",
        "status": "confirmed",
        "is_manual": False,
        "related_files": [],
    }
    return DeadlineOut(**{**data, **overrides})


def events_of(data: bytes) -> list[Event]:
    components = Calendar.from_ical(data).walk("VEVENT")
    assert all(isinstance(component, Event) for component in components)
    return [component for component in components if isinstance(component, Event)]


def test_empty_list_gives_valid_calendar_without_events() -> None:
    data = export_ics([])
    assert data.startswith(b"BEGIN:VCALENDAR")
    assert events_of(data) == []


def test_deadline_without_date_is_skipped() -> None:
    data = export_ics([make_deadline(due_date=None, status="undefined")])
    assert events_of(data) == []


def test_invalid_date_is_skipped() -> None:
    data = export_ics([make_deadline(due_date="not-a-date")])
    assert events_of(data) == []


def test_date_only_deadline_becomes_all_day_event() -> None:
    (event,) = events_of(export_ics([make_deadline()]))
    assert event.get("dtstart").dt == date(2026, 11, 10)
    assert event.get("dtend").dt == date(2026, 11, 11)
    assert str(event.get("summary")) == "Project proposal"


def test_deadline_with_time_keeps_time_and_timezone() -> None:
    (event,) = events_of(export_ics([make_deadline(due_date="2026-11-10T23:59")]))
    start = event.get("dtstart").dt
    assert (start.hour, start.minute) == (23, 59)
    assert start.utcoffset().total_seconds() == 3 * 3600


def test_description_lists_requirements_and_source_page() -> None:
    (event,) = events_of(export_ics([make_deadline()]))
    description = str(event.get("description"))
    assert "- Dockerfile" in description
    assert "стр. 2" in description


def test_manual_deadline_is_exported_without_page_reference() -> None:
    deadline = make_deadline(file_id=None, source_page=None, source_quote=None, is_manual=True)
    (event,) = events_of(export_ics([deadline]))
    description = str(event.get("description"))
    assert "Добавлено вручную" in description
    assert "стр." not in description
    assert "None" not in description


def test_unconfirmed_date_is_marked_in_description() -> None:
    deadline = make_deadline(status="needs_confirmation", date_note="in two weeks")
    (event,) = events_of(export_ics([deadline]))
    description = str(event.get("description"))
    assert "требует подтверждения" in description
    assert "in two weeks" in description


def test_events_have_unique_uids() -> None:
    data = export_ics(
        [
            make_deadline(id=UUID("00000000-0000-0000-0000-000000000001")),
            make_deadline(id=UUID("00000000-0000-0000-0000-000000000002")),
        ]
    )
    uids = {str(event.get("uid")) for event in events_of(data)}
    assert len(uids) == 2
