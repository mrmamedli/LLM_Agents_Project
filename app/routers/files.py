from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from app.config import Settings, get_settings
from app.models import Deadline, DocumentFile, Subject, deadline_related_files
from app.schemas import DeadlineOut, FileCard, FileOut, SummaryOut
from app.security import CurrentUser, DatabaseSession
from app.services.processing import process_file
from app.services.storage import delete_file, save_upload

router = APIRouter(tags=["Files"])
AppSettings = Annotated[Settings, Depends(get_settings)]


async def get_owned_subject(subject_id: UUID, db: DatabaseSession, user_id: UUID) -> Subject:
    subject = await db.scalar(
        select(Subject).where(Subject.id == subject_id, Subject.user_id == user_id)
    )
    if subject is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subject not found")
    return subject


async def get_owned_file(file_id: UUID, db: DatabaseSession, user_id: UUID) -> DocumentFile:
    document = await db.scalar(
        select(DocumentFile)
        .join(Subject)
        .where(DocumentFile.id == file_id, Subject.user_id == user_id)
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return document


@router.get(
    "/api/subjects/{id}/files",
    response_model=list[FileOut],
    operation_id="listSubjectFiles",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Subject not found"}},
)
async def list_subject_files(
    id: UUID,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> list[DocumentFile]:
    await get_owned_subject(id, db, current_user.id)
    files = await db.scalars(
        select(DocumentFile)
        .where(DocumentFile.subject_id == id)
        .order_by(DocumentFile.created_at, DocumentFile.id)
    )
    return list(files)


@router.post(
    "/api/subjects/{id}/files",
    response_model=FileOut,
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="uploadSubjectFile",
    responses={
        status.HTTP_400_BAD_REQUEST: {"description": "File must have a .pdf extension"},
        status.HTTP_404_NOT_FOUND: {"description": "Subject not found"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "Unsupported media type"},
    },
)
async def upload_subject_file(
    id: UUID,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    current_user: CurrentUser,
    settings: AppSettings,
    file: UploadFile = File(...),
) -> DocumentFile:
    await get_owned_subject(id, db, current_user.id)
    filename = file.filename
    if filename is None or not filename.lower().endswith(".pdf"):
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must have a .pdf extension",
        )
    if file.content_type != "application/pdf":
        await file.close()
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only application/pdf uploads are supported",
        )

    storage_key = await save_upload(file, settings.storage_path)
    document = DocumentFile(subject_id=id, filename=filename, storage_key=storage_key)
    db.add(document)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        delete_file(settings.storage_path, storage_key)
        raise

    background_tasks.add_task(process_file, document.id)
    return document


@router.get(
    "/api/files/{id}",
    response_model=FileCard,
    operation_id="getFileCard",
    responses={status.HTTP_404_NOT_FOUND: {"description": "File not found"}},
)
async def get_file_card(id: UUID, db: DatabaseSession, current_user: CurrentUser) -> FileCard:
    document = await db.scalar(
        select(DocumentFile)
        .join(Subject)
        .where(DocumentFile.id == id, Subject.user_id == current_user.id)
        .options(selectinload(DocumentFile.deadlines).selectinload(Deadline.related_files))
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    summary = None
    if document.summary_text is not None:
        summary = SummaryOut(
            text=document.summary_text,
            key_terms=document.summary_key_terms or [],
        )
    return FileCard(
        file=FileOut.model_validate(document),
        summary=summary,
        deadlines=[DeadlineOut.model_validate(deadline) for deadline in document.deadlines],
    )


@router.post(
    "/api/files/{id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    operation_id="reprocessFile",
    responses={status.HTTP_404_NOT_FOUND: {"description": "File not found"}},
)
async def reprocess_file(
    id: UUID,
    background_tasks: BackgroundTasks,
    db: DatabaseSession,
    current_user: CurrentUser,
) -> Response:
    document = await get_owned_file(id, db, current_user.id)
    agent_deadlines = (Deadline.file_id == document.id, Deadline.is_manual.is_(False))
    deadline_ids = select(Deadline.id).where(*agent_deadlines)
    await db.execute(
        delete(deadline_related_files).where(deadline_related_files.c.deadline_id.in_(deadline_ids))
    )
    await db.execute(delete(Deadline).where(*agent_deadlines))
    document.status = "uploaded"
    document.doc_type = None
    document.error = None
    document.summary_text = None
    document.summary_key_terms = None
    await db.commit()

    background_tasks.add_task(process_file, document.id)
    return Response(status_code=status.HTTP_202_ACCEPTED)
