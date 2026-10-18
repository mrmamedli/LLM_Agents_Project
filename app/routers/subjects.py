from uuid import UUID

from fastapi import APIRouter, Response, status

from app.routers.common import SessionId, not_implemented
from app.schemas import SubjectCreate, SubjectOut

router = APIRouter(prefix="/api/subjects", tags=["Subjects"])


@router.get("", response_model=list[SubjectOut], operation_id="listSubjects")
async def list_subjects(session_id: SessionId) -> list[SubjectOut]:
    del session_id
    not_implemented()


@router.post(
    "", response_model=SubjectOut, status_code=status.HTTP_201_CREATED, operation_id="createSubject"
)
async def create_subject(payload: SubjectCreate, session_id: SessionId) -> SubjectOut:
    del payload, session_id
    not_implemented()


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="deleteSubject")
async def delete_subject(id: UUID, session_id: SessionId) -> Response:
    del id, session_id
    not_implemented()
