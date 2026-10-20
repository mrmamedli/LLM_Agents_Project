from datetime import UTC, date, datetime, timedelta
from typing import cast
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from app.schemas import DeadlineOut

TIMEZONE = ZoneInfo("Europe/Moscow")
TIMED_EVENT_DURATION = timedelta(hours=1)


def export_ics(deadlines: list[DeadlineOut]) -> bytes:
    """Build an iCalendar file. Deadlines without a valid date are skipped."""
    calendar = Calendar()
    calendar.add("prodid", "-//StudyHub//Deadlines//RU")
    calendar.add("version", "2.0")
    calendar.add("x-wr-calname", "StudyHub: дедлайны")

    for deadline in deadlines:
        event = _build_event(deadline)
        if event is not None:
            calendar.add_component(event)
    return cast(bytes, calendar.to_ical())


def _parse_due(value: str) -> date | datetime | None:
    try:
        if "T" in value:
            parsed = datetime.fromisoformat(value)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=TIMEZONE)
        return date.fromisoformat(value)
    except ValueError:
        return None


def _build_event(deadline: DeadlineOut) -> Event | None:
    if not deadline.due_date:
        return None
    due = _parse_due(deadline.due_date)
    if due is None:
        return None

    duration = TIMED_EVENT_DURATION if isinstance(due, datetime) else timedelta(days=1)
    event = Event()
    event.add("uid", f"deadline-{deadline.id}@studyhub")
    event.add("dtstamp", datetime.now(UTC))
    event.add("summary", deadline.title)
    event.add("dtstart", due)
    event.add("dtend", due + duration)
    event.add("description", _description(deadline))
    return event


def _description(deadline: DeadlineOut) -> str:
    lines: list[str] = []
    if deadline.requirements:
        lines.append("Требования:")
        lines.extend(f"- {requirement}" for requirement in deadline.requirements)
    lines.append(
        "Добавлено вручную" if deadline.is_manual else f"Источник: стр. {deadline.source_page}"
    )
    if deadline.status == "needs_confirmation":
        note = f" (в документе: {deadline.date_note})" if deadline.date_note else ""
        lines.append(f"Дата требует подтверждения{note}")
    return "\n".join(lines)
