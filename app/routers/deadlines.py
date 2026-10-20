from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.models import Deadline, DocumentFile, Subject, deadline_related_files
from app.schemas import DeadlineCreate, DeadlineOut, DeadlineUpdate
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


@router.post(
    "",
    response_model=DeadlineOut,
    status_code=status.HTTP_201_CREATED,
    operation_id="createDeadline",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Subject or file not found"}},
)
async def create_deadline(
    payload: DeadlineCreate,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Deadline:
    subject = await db.scalar(
        select(Subject).where(Subject.id == payload.subject_id, Subject.user_id == current_user.id)
    )
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    if payload.file_id is not None:
        file_id = await db.scalar(
            select(DocumentFile.id).where(
                DocumentFile.id == payload.file_id, DocumentFile.subject_id == subject.id
            )
        )
        if file_id is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    deadline = Deadline(
        file_id=payload.file_id,
        subject_id=subject.id,
        title=payload.title,
        due_date=payload.due_date,
        date_note=None,
        requirements=payload.requirements,
        source_page=None,
        source_quote=None,
        status="confirmed" if payload.due_date else "undefined",
        is_manual=True,
        related_files=[],
    )
    db.add(deadline)
    await db.commit()
    return deadline


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


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteDeadline",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Deadline not found"}},
)
async def delete_deadline(id: UUID, db: DatabaseSession, current_user: CurrentUser) -> Response:
    owned_id = await db.scalar(
        select(Deadline.id)
        .join(Subject, Deadline.subject_id == Subject.id)
        .where(Deadline.id == id, Subject.user_id == current_user.id)
    )
    if owned_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deadline not found")

    await db.execute(
        delete(deadline_related_files).where(deadline_related_files.c.deadline_id == owned_id)
    )
    await db.execute(delete(Deadline).where(Deadline.id == owned_id))
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
