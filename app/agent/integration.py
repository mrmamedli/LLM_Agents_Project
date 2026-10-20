"""Реализация Repository на SQLAlchemy + S3/Minio.

Использует ваши реальные модели (app.models):
  Subject, DocumentFile (таблица files), Deadline, User

Предполагается, что у вас уже есть:
  • async SQLAlchemy сессия (DatabaseSession в app.security)
  • S3/Minio-клиент с методом download_fileobj/get_object — см. ниже в _download_pdf
  • Pydantic-схемы SubjectOut/FileOut/DeadlineOut — используются в роутерах

Структура:
  AsyncSqlAlchemyRepository — реализация Repository под ваши модели.
  StorageClient — тонкая обёртка над S3/Minio для скачивания PDF по storage_key.

Запуск агента из роутера:
  POST /api/subjects/{id}/files:
    1. Сохранить PDF в S3 → получить storage_key
    2. Создать DocumentFile(status='uploaded', storage_key=...)
    3. background_tasks.add_task(run_agent, file_id, user_id)

  run_agent() — отдельная async-функция, которая создаёт новую сессию БД
  (сессия из Depends закроется после возврата ответа), создаёт репозиторий
  и вызывает process_file().
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .repository import DeadlineRecord, FileRecord, Repository

if TYPE_CHECKING:
    from app.models import Deadline

# ============================================================================
# Storage-клиент: скачивание PDF из S3/Minio по storage_key
# ============================================================================


class StorageClient:
    """Тонкая обёртка над локальным хранилищем для скачивания PDF.

    Адаптируйте под ваш реальный storage-сервис. Возможные варианты:

    Вариант A — boto3 (sync) через asyncio.to_thread:
        import boto3, asyncio
        self._client = boto3.client("s3", ...)
        async def download(self, key: str) -> bytes:
            return await asyncio.to_thread(self._download_sync, key)
        def _download_sync(self, key):
            obj = self._client.get_object(Bucket=self._bucket, Key=key)
            return obj["Body"].read()

    Вариант B — aiobotocore (native async):
        async with self._client.get_object(Bucket=..., Key=...) as resp:
            return await resp["Body"].read()

    Вариант C — minio-py (sync) через to_thread:
        from minio import Minio
        self._client = Minio(...)
        async def download(self, key: str) -> bytes:
            return await asyncio.to_thread(
                lambda: self._client.get_object(self._bucket, key).read()
            )

    Вариант D — файлы на диске (для локальной разработки):
        async def download(self, key: str) -> bytes:
            return Path(key).read_bytes()
    """

    def __init__(self, root: Path):
        self._root = root

    async def download(self, storage_key: str) -> bytes | None:
        """Скачивает объект по storage_key, возвращает bytes или None при ошибке.

        РЕАЛИЗУЙТЕ под ваш storage. Заглушка ниже читает файл с диска —
        замените на реальный S3/Minio вызов.
        """
        try:
            return (self._root / storage_key).read_bytes()
        except OSError:
            return None


# Глобальный синглтон storage-клиента — инициализируется в app startup.
# (Если у вас уже есть storage-сервис в app.services — используйте его вместо этого класса.)
_storage_client: StorageClient | None = None


def get_storage_client() -> StorageClient:
    global _storage_client
    if _storage_client is None:
        from app.config import get_settings

        _storage_client = StorageClient(root=get_settings().storage_path)
    return _storage_client


def set_storage_client(client: StorageClient) -> None:
    """Для тестов/старта — позволяет подменить клиент."""
    global _storage_client
    _storage_client = client


# ============================================================================
# AsyncSqlAlchemyRepository — реализация Repository под ваши модели
# ============================================================================


class AsyncSqlAlchemyRepository(Repository):
    """Реализация Repository под async SQLAlchemy и ваши модели.

    Использование:
        async with AsyncSessionLocal() as db:
            repo = AsyncSqlAlchemyRepository(db, storage=get_storage_client())
            await process_file(file_id, repo, owner_id)
    """

    def __init__(self, db: AsyncSession, storage: StorageClient | None = None):
        """
        Аргументы:
          db      — открытая async SQLAlchemy-сессия;
          storage — клиент S3/Minio для скачивания PDF. Если None — берётся глобальный.
        """
        self.db = db
        self.storage = storage or get_storage_client()

    # ---------- Вспомогательное: проверка ownership через Subject.user_id ----------

    async def _check_file_owner(self, file_id: str, owner_id: str) -> bool:
        """Проверяет, что файл принадлежит пользователю через Subject.user_id."""
        from app.models import DocumentFile, Subject

        stmt = (
            select(Subject.user_id)
            .join(DocumentFile, DocumentFile.subject_id == Subject.id)
            .where(DocumentFile.id == uuid.UUID(file_id))
        )
        user_id = (await self.db.execute(stmt)).scalar_one_or_none()
        return user_id is not None and str(user_id) == str(owner_id)

    # ---------- Файлы ----------

    async def get_file(self, file_id: str) -> FileRecord | None:
        from app.models import DocumentFile

        f = await self.db.get(DocumentFile, uuid.UUID(file_id))
        if f is None:
            return None
        return FileRecord(
            id=str(f.id),
            subject_id=str(f.subject_id),
            filename=f.filename,
            storage_key=f.storage_key,
            status=f.status,
            doc_type=f.doc_type,
            error=f.error,
        )

    async def get_pdf_bytes(self, file_id: str) -> bytes | None:
        """Скачивает бинарь PDF из S3/Minio по storage_key файла."""
        from app.models import DocumentFile

        f = await self.db.get(DocumentFile, uuid.UUID(file_id))
        if f is None or not f.storage_key:
            return None
        return await self.storage.download(f.storage_key)

    async def set_file_status(
        self,
        file_id: str,
        status: str,
        *,
        doc_type: str | None = None,
        error: str | None = None,
    ) -> None:
        from app.models import DocumentFile

        values: dict[str, object] = {"status": status}
        if doc_type is not None:
            values["doc_type"] = doc_type
        if error is not None:
            values["error"] = error
        await self.db.execute(
            update(DocumentFile).where(DocumentFile.id == uuid.UUID(file_id)).values(**values)
        )
        await self.db.commit()

    async def list_files_of_subject(self, subject_id: str, owner_id: str) -> list[FileRecord]:
        """Файлы предмета, принадлежащие пользователю (через Subject.user_id)."""
        from app.models import DocumentFile, Subject

        stmt = (
            select(DocumentFile)
            .join(Subject, DocumentFile.subject_id == Subject.id)
            .where(
                DocumentFile.subject_id == uuid.UUID(subject_id),
                Subject.user_id == uuid.UUID(owner_id),
            )
            .order_by(DocumentFile.created_at.desc())
        )
        result = await self.db.scalars(stmt)
        return [
            FileRecord(
                id=str(f.id),
                subject_id=str(f.subject_id),
                filename=f.filename,
                storage_key=f.storage_key,
                status=f.status,
                doc_type=f.doc_type,
                error=f.error,
            )
            for f in result
        ]

    # ---------- Конспект (поля DocumentFile.summary_text / summary_key_terms) ----------

    async def save_summary(self, file_id: str, text: str, key_terms: list[str]) -> None:
        """Сохраняет конспект в поля файла."""
        from app.models import DocumentFile

        await self.db.execute(
            update(DocumentFile)
            .where(DocumentFile.id == uuid.UUID(file_id))
            .values(summary_text=text, summary_key_terms=key_terms)
        )
        await self.db.commit()

    async def get_summary(self, file_id: str) -> dict[str, object] | None:
        from app.models import DocumentFile

        f = await self.db.get(DocumentFile, uuid.UUID(file_id))
        if f is None or f.summary_text is None:
            return None
        return {"text": f.summary_text, "key_terms": f.summary_key_terms or []}

    # ---------- Дедлайны ----------

    async def save_deadline(
        self,
        file_id: str,
        subject_id: str,
        owner_id: str,
        title: str,
        due_date: str | None,
        date_note: str | None,
        requirements: list[str],
        source_page: int,
        source_quote: str,
        status: str = "pending",
    ) -> str:
        """Создаёт Deadline. owner_id используется только для проверки ownership."""
        from app.models import Deadline

        # Проверяем, что файл принадлежит пользователю.
        if not await self._check_file_owner(file_id, owner_id):
            raise PermissionError(f"file_id={file_id} не принадлежит user_id={owner_id}")

        d = Deadline(
            id=uuid.uuid4(),
            file_id=uuid.UUID(file_id),
            subject_id=uuid.UUID(subject_id),
            title=title,
            due_date=due_date,
            date_note=date_note,
            requirements=requirements,
            source_page=source_page,
            source_quote=source_quote,
            status=status,
        )
        self.db.add(d)
        await self.db.commit()
        return str(d.id)

    async def get_deadline(self, deadline_id: str) -> DeadlineRecord | None:
        from app.models import Deadline

        d = await self.db.get(
            Deadline,
            uuid.UUID(deadline_id),
            options=[selectinload(Deadline.related_files)],
        )
        if d is None:
            return None
        return self._deadline_to_record(d)

    async def list_deadlines_of_file(self, file_id: str, owner_id: str) -> list[DeadlineRecord]:
        from app.models import Deadline, DocumentFile, Subject

        stmt = (
            select(Deadline)
            .join(DocumentFile, Deadline.file_id == DocumentFile.id)
            .join(Subject, DocumentFile.subject_id == Subject.id)
            .where(
                Deadline.file_id == uuid.UUID(file_id),
                Subject.user_id == uuid.UUID(owner_id),
            )
            .options(selectinload(Deadline.related_files))
            .order_by(Deadline.source_page)
        )
        result = await self.db.scalars(stmt)
        return [self._deadline_to_record(d) for d in result]

    async def clear_file_results(self, file_id: str, owner_id: str) -> None:
        """Стирает конспект и удаляет дедлайны файла (перед reprocess)."""
        from app.models import Deadline, DocumentFile

        if not await self._check_file_owner(file_id, owner_id):
            raise PermissionError(f"file_id={file_id} не принадлежит user_id={owner_id}")

        # 1. Сбрасываем summary_text / summary_key_terms в NULL.
        await self.db.execute(
            update(DocumentFile)
            .where(DocumentFile.id == uuid.UUID(file_id))
            .values(summary_text=None, summary_key_terms=None)
        )
        # 2. Удаляем дедлайны файла (M2M related_files очистится каскадно через ondelete CASCADE).
        await self.db.execute(delete(Deadline).where(Deadline.file_id == uuid.UUID(file_id)))
        await self.db.commit()

    def _deadline_to_record(self, d: Deadline) -> DeadlineRecord:
        return DeadlineRecord(
            id=str(d.id),
            file_id=str(d.file_id),
            subject_id=str(d.subject_id),
            title=d.title,
            due_date=d.due_date,
            date_note=d.date_note,
            requirements=d.requirements or [],
            source_page=d.source_page or 1,
            source_quote=d.source_quote or "",
            status=d.status,
            related_file_ids=[str(f.id) for f in (d.related_files or [])],
        )

    # ---------- Связи дедлайн ↔ файлы (M2M через deadline_related_files) ----------

    async def link_related_files(
        self, deadline_id: str, owner_id: str, file_ids: list[str]
    ) -> None:
        """Добавляет файлы в deadline.related_files.
        Файлы проверяются на ownership через subject.user_id.
        """
        from app.models import Deadline, DocumentFile, Subject

        d = await self.db.get(
            Deadline,
            uuid.UUID(deadline_id),
            options=[selectinload(Deadline.related_files)],
        )
        if d is None:
            return

        existing_ids = {str(f.id) for f in d.related_files}

        # Загружаем все файлы, которые хотим добавить, с проверкой ownership.
        stmt = (
            select(DocumentFile)
            .join(Subject, DocumentFile.subject_id == Subject.id)
            .where(
                DocumentFile.id.in_([uuid.UUID(fid) for fid in file_ids]),
                Subject.user_id == uuid.UUID(owner_id),
            )
        )
        files_to_add = list(await self.db.scalars(stmt))

        for f in files_to_add:
            if str(f.id) not in existing_ids:
                d.related_files.append(f)

        await self.db.commit()
