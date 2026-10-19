from uuid import UUID

from fastapi import APIRouter, Response
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Deadline, Subject
from app.schemas import DeadlineOut
from app.security import CurrentUser, DatabaseSession
from app.services.ics_export import export_ics

router = APIRouter(tags=["Calendar"])


class CalendarResponse(Response):
    media_type = "text/calendar"


@router.get("/api/calendar.ics", response_class=CalendarResponse, operation_id="exportCalendar")
async def export_calendar(
    db: DatabaseSession,
    current_user: CurrentUser,
    subject_id: UUID | None = None,
) -> Response:
    statement = (
        select(Deadline)
        .join(Subject, Deadline.subject_id == Subject.id)
        .where(Subject.user_id == current_user.id)
        .options(selectinload(Deadline.related_files))
        .order_by(Deadline.id)
    )
    if subject_id is not None:
        statement = statement.where(Deadline.subject_id == subject_id)

    deadlines = list(await db.scalars(statement))
    content = export_ics([DeadlineOut.model_validate(deadline) for deadline in deadlines])
    return CalendarResponse(
        content=content,
        headers={"Content-Disposition": 'attachment; filename="studyhub-deadlines.ics"'},
    )
