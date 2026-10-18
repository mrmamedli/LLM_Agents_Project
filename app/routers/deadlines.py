from uuid import UUID

from fastapi import APIRouter

from app.routers.common import SessionId, not_implemented
from app.schemas import DeadlineOut, DeadlineUpdate

router = APIRouter(prefix="/api/deadlines", tags=["Deadlines"])


@router.get("", response_model=list[DeadlineOut], operation_id="listDeadlines")
async def list_deadlines(
    session_id: SessionId, subject_id: UUID | None = None
) -> list[DeadlineOut]:
    del session_id, subject_id
    not_implemented()


@router.patch("/{id}", response_model=DeadlineOut, operation_id="updateDeadline")
async def update_deadline(id: UUID, payload: DeadlineUpdate, session_id: SessionId) -> DeadlineOut:
    del id, payload, session_id
    not_implemented()
