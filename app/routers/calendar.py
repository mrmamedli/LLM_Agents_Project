from uuid import UUID

from fastapi import APIRouter, Response

from app.routers.common import SessionId, not_implemented

router = APIRouter(tags=["Calendar"])


@router.get("/api/calendar.ics", response_class=Response, operation_id="exportCalendar")
async def export_calendar(session_id: SessionId, subject_id: UUID | None = None) -> Response:
    del session_id, subject_id
    not_implemented()
