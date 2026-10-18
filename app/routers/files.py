from uuid import UUID

from fastapi import APIRouter, File, UploadFile, status

from app.routers.common import SessionId, not_implemented
from app.schemas import FileCard, FileOut

router = APIRouter(tags=["Files"])


@router.get(
    "/api/subjects/{id}/files", response_model=list[FileOut], operation_id="listSubjectFiles"
)
async def list_subject_files(id: UUID, session_id: SessionId) -> list[FileOut]:
    del id, session_id
    not_implemented()


@router.post(
    "/api/subjects/{id}/files",
    response_model=FileOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadSubjectFile",
)
async def upload_subject_file(
    id: UUID, session_id: SessionId, file: UploadFile = File(...)
) -> FileOut:
    del id, session_id, file
    not_implemented()


@router.get("/api/files/{id}", response_model=FileCard, operation_id="getFileCard")
async def get_file_card(id: UUID, session_id: SessionId) -> FileCard:
    del id, session_id
    not_implemented()


@router.post(
    "/api/files/{id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="reprocessFile",
)
async def reprocess_file(id: UUID, session_id: SessionId) -> None:
    del id, session_id
    not_implemented()
