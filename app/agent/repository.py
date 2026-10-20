"""Абстрактный репозиторий — интерфейс между агентом и БД вашего проекта.

Адаптировано под ваши модели (app.models):
  User → Subject → DocumentFile (с полями summary_text/summary_key_terms) → Deadline
  M2M: Deadline.related_files ↔ DocumentFile через таблицу deadline_related_files

Ключевые отличия от первой версии:
  • Все методы async (у вас async SQLAlchemy).
  • Вместо pdf_path — get_pdf_bytes(): в вашей схеме файлы в S3/Minio по storage_key,
    поэтому репозиторий сам скачивает бинарь и отдаёт bytes.
  • Owner определяется через Subject.user_id (у DocumentFile/Deadline нет своего user_id).
    owner_id передаётся один раз в process_file() и в build_tools() — для авторизации
    в инструментах list_files_of_subject / link_related_files.
  • Конспект сохраняется в полях DocumentFile.summary_text/summary_key_terms
    (отдельной таблицы Summary нет).
  • source_page у Deadline — int (not null), агент обязан всегда передавать номер страницы.
  • due_date — String(64), хранится как ISO 'YYYY-MM-DD' или None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol, runtime_checkable


# ---------- DTO: то, что агент получает от репозитория ----------

@dataclass
class FileRecord:
    """Метаданные файла — соответствует DocumentFile + нужные агенту поля."""
    id: str                       # UUID (как строка для совместимости с tool-схемой)
    subject_id: str               # UUID
    filename: str
    storage_key: str              # ключ в S3/Minio (для скачивания бинаря)
    status: str                   # 'uploaded' | 'processing' | 'processed' | 'failed'
    doc_type: Optional[str] = None
    error: Optional[str] = None


@dataclass
class DeadlineRecord:
    """Дедлайн — соответствует модели Deadline."""
    id: str
    file_id: str
    subject_id: str
    title: str
    due_date: Optional[str]       # ISO 'YYYY-MM-DD' или None
    date_note: Optional[str]
    requirements: list[str] = field(default_factory=list)
    source_page: int = 1          # не null в вашей схеме — по умолчанию 1
    source_quote: str = ""
    status: str = "pending"
    related_file_ids: list[str] = field(default_factory=list)


# ---------- Protocol репозитория ----------

@runtime_checkable
class Repository(Protocol):
    """Async-интерфейс доступа к данным проекта.

    Все методы — async def. Реализуйте под async SQLAlchemy (см. integration.py).
    """

    # ---- Файлы ----

    async def get_file(self, file_id: str) -> Optional[FileRecord]:
        """Возвращает метаданные файла или None.
        Owner проверяется отдельно через owner_id в вызывающем коде.
        """
        ...

    async def get_pdf_bytes(self, file_id: str) -> Optional[bytes]:
        """Скачивает бинарь PDF из S3/Minio по storage_key и возвращает bytes.
        Возвращает None, если файл не найден или не удалось скачать.
        """
        ...

    async def set_file_status(self, file_id: str, status: str, *,
                              doc_type: Optional[str] = None,
                              error: Optional[str] = None) -> None:
        """Обновляет статус файла. doc_type/error передаются только если не None.
        Также если status='processed' и есть summary — он уже сохранён ранее.
        """
        ...

    async def list_files_of_subject(self, subject_id: str, owner_id: str) -> list[FileRecord]:
        """Файлы предмета, принадлежащие пользователю (через Subject.user_id).
        Используется инструментом list_materials.
        """
        ...

    # ---- Конспект (поля DocumentFile.summary_text / summary_key_terms) ----

    async def save_summary(self, file_id: str, text: str, key_terms: list[str]) -> None:
        """Сохраняет конспект в поля DocumentFile.summary_text / summary_key_terms."""
        ...

    async def get_summary(self, file_id: str) -> Optional[dict]:
        """Возвращает {text, key_terms} из полей файла, или None если конспекта нет."""
        ...

    # ---- Дедлайны (модель Deadline) ----

    async def save_deadline(
        self,
        file_id: str,
        subject_id: str,
        owner_id: str,
        title: str,
        due_date: Optional[str],
        date_note: Optional[str],
        requirements: list[str],
        source_page: int,
        source_quote: str,
        status: str = "pending",
    ) -> str:
        """Создаёт Deadline, возвращает его UUID как строку."""
        ...

    async def get_deadline(self, deadline_id: str) -> Optional[DeadlineRecord]:
        """Возвращает дедлайн по UUID или None."""
        ...

    async def list_deadlines_of_file(self, file_id: str, owner_id: str) -> list[DeadlineRecord]:
        """Дедлайны файла, принадлежащие пользователю.
        Owner проверяется через JOIN file → subject → user_id.
        """
        ...

    async def clear_file_results(self, file_id: str, owner_id: str) -> None:
        """Стирает конспект (summary_text/key_terms → None) и удаляет дедлайны файла.
        Вызывается перед повторной обработкой (POST /api/files/{id}/reprocess).
        """
        ...

    # ---- Связи дедлайн ↔ файлы (M2M через deadline_related_files) ----

    async def link_related_files(self, deadline_id: str, owner_id: str,
                                 file_ids: list[str]) -> None:
        """Добавляет file_ids в deadline.related_files.
        Пропускает file_id, не принадлежащие owner_id (проверка через subject.user_id).
        """
        ...
