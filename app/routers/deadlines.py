from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import Deadline, Subject
from app.schemas import DeadlineOut, DeadlineUpdate
from app.security import CurrentUser, DatabaseSession

router = APIRouter(prefix="/api/deadlines", tags=["Deadlines"])


@router.get("", response_model=list[DeadlineOut], operation_id="listDeadlines")
async def list_deadlines(
    db: DatabaseSession,
    current_user: CurrentUser,
    subject_id: UUID | None = None,
) -> list[Deadline]:
    statement = (
        select(Deadline)
        .join(Subject, Deadline.subject_id == Subject.id)
        .where(Subject.user_id == current_user.id)
        .options(selectinload(Deadline.related_files))
        .order_by(Deadline.id)
    )
    if subject_id is not None:
        statement = statement.where(Deadline.subject_id == subject_id)
    return list(await db.scalars(statement))


@router.patch(
    "/{id}",
    response_model=DeadlineOut,
    operation_id="updateDeadline",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Deadline not found"}},
)
async def update_deadline(
    id: UUID,
    payload: DeadlineUpdate,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Deadline:
    deadline = await db.scalar(
        select(Deadline)
        .join(Subject, Deadline.subject_id == Subject.id)
        .where(Deadline.id == id, Subject.user_id == current_user.id)
        .options(selectinload(Deadline.related_files))
    )
    if deadline is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")

    deadline.due_date = payload.due_date
    deadline.status = payload.status
    await db.commit()
    return deadline
