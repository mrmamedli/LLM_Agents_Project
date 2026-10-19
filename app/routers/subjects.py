from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy import select

from app.models import Subject
from app.schemas import SubjectCreate, SubjectOut
from app.security import CurrentUser, DatabaseSession

router = APIRouter(prefix="/api/subjects", tags=["Subjects"])


@router.get("", response_model=list[SubjectOut], operation_id="listSubjects")
async def list_subjects(db: DatabaseSession, current_user: CurrentUser) -> list[Subject]:
    subjects = await db.scalars(
        select(Subject)
        .where(Subject.user_id == current_user.id)
        .order_by(Subject.created_at, Subject.id)
    )
    return list(subjects)


@router.post(
    "", response_model=SubjectOut, status_code=status.HTTP_201_CREATED, operation_id="createSubject"
)
async def create_subject(
    payload: SubjectCreate,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Subject:
    subject = Subject(user_id=current_user.id, name=payload.name)
    db.add(subject)
    await db.commit()
    return subject


@router.delete(
    "/{id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id="deleteSubject",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Subject not found"}},
)
async def delete_subject(
    id: UUID,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    subject = await db.scalar(
        select(Subject).where(Subject.id == id, Subject.user_id == current_user.id)
    )
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")

    await db.delete(subject)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
