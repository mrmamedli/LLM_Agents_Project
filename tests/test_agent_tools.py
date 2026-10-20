from pathlib import Path
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.integration import AsyncSqlAlchemyRepository, StorageClient
from app.models import DocumentFile, Subject
from tests.conftest import AuthorizedSession, TestSessionFactory


async def test_storage_client_reads_keys_relative_to_storage_root(tmp_path: Path) -> None:
    storage_root = tmp_path / "uploads"
    storage_root.mkdir()
    (storage_root / "document.pdf").write_bytes(b"%PDF-1.4 test")

    storage = StorageClient(storage_root)

    assert await storage.download("document.pdf") == b"%PDF-1.4 test"
    assert await storage.download("missing.pdf") is None


async def test_repository_reads_uploaded_pdf_from_configured_storage_root(
    database: None,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
    tmp_path: Path,
) -> None:
    del database
    storage_root = tmp_path / "uploads"
    storage_root.mkdir()
    storage_key = f"{uuid4()}.pdf"
    pdf_bytes = b"%PDF-1.4 stored document"
    (storage_root / storage_key).write_bytes(pdf_bytes)

    async with test_session_factory() as db:
        document = await _create_document(db, authorized_session, storage_key)
        repository = AsyncSqlAlchemyRepository(db, storage=StorageClient(storage_root))

        assert await repository.get_pdf_bytes(str(document.id)) == pdf_bytes


async def _create_document(
    db: AsyncSession,
    authorized_session: AuthorizedSession,
    storage_key: str,
) -> DocumentFile:
    subject = Subject(user_id=authorized_session.user.id, name="Databases")
    db.add(subject)
    await db.flush()
    document = DocumentFile(
        subject_id=subject.id,
        filename="document.pdf",
        storage_key=storage_key,
    )
    db.add(document)
    await db.commit()
    return document
