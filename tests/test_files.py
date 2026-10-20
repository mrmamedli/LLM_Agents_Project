from uuid import UUID, uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.config import Settings
from app.models import Deadline, DocumentFile, Subject
from tests.conftest import AuthorizedSession, AuthorizedSessionFactory, TestSessionFactory


@pytest.fixture
def processed_file_ids(monkeypatch: pytest.MonkeyPatch) -> list[UUID]:
    processed: list[UUID] = []
    monkeypatch.setattr("app.routers.files.process_file", processed.append)
    return processed


async def create_subject(
    test_session_factory: TestSessionFactory,
    user_id: UUID,
    name: str = "Databases",
) -> Subject:
    async with test_session_factory() as db:
        subject = Subject(user_id=user_id, name=name)
        db.add(subject)
        await db.commit()
        return subject


async def create_document(
    test_session_factory: TestSessionFactory,
    subject_id: UUID,
    *,
    filename: str = "lecture.pdf",
    status: str = "uploaded",
) -> DocumentFile:
    async with test_session_factory() as db:
        document = DocumentFile(
            subject_id=subject_id,
            filename=filename,
            storage_key=f"{uuid4()}.pdf",
            status=status,
        )
        db.add(document)
        await db.commit()
        return document


async def test_file_endpoints_require_authentication(client: AsyncClient) -> None:
    resource_id = "00000000-0000-0000-0000-000000000001"

    assert (await client.get(f"/api/subjects/{resource_id}/files")).status_code == 401
    upload = await client.post(
        f"/api/subjects/{resource_id}/files",
        files={"file": ("lecture.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert upload.status_code == 401
    assert (await client.get(f"/api/files/{resource_id}")).status_code == 401
    assert (await client.post(f"/api/files/{resource_id}/reprocess")).status_code == 401


async def test_upload_validates_file_and_subject_ownership(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    subject = await create_subject(test_session_factory, authorized_session.user.id)
    other = await authorized_session_factory("other@example.com", "other-session")

    wrong_extension = await client.post(
        f"/api/subjects/{subject.id}/files",
        files={"file": ("notes.txt", b"content", "application/pdf")},
        headers=authorized_session.headers,
    )
    wrong_media_type = await client.post(
        f"/api/subjects/{subject.id}/files",
        files={"file": ("notes.pdf", b"content", "text/plain")},
        headers=authorized_session.headers,
    )
    foreign_subject = await client.post(
        f"/api/subjects/{subject.id}/files",
        files={"file": ("notes.txt", b"content", "text/plain")},
        headers=other.headers,
    )
    foreign_list = await client.get(
        f"/api/subjects/{subject.id}/files",
        headers=other.headers,
    )

    assert wrong_extension.status_code == 400
    assert wrong_media_type.status_code == 415
    assert foreign_subject.status_code == 404
    assert foreign_list.status_code == 404


async def test_upload_and_list_files_for_owned_subject(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
    test_settings: Settings,
    processed_file_ids: list[UUID],
) -> None:
    subject = await create_subject(test_session_factory, authorized_session.user.id)
    upload = await client.post(
        f"/api/subjects/{subject.id}/files",
        files={"file": ("lecture.PDF", b"%PDF-1.4 stub", "application/pdf")},
        headers=authorized_session.headers,
    )

    assert upload.status_code == 202
    uploaded = upload.json()
    assert uploaded == {
        "id": uploaded["id"],
        "subject_id": str(subject.id),
        "filename": "lecture.PDF",
        "status": "uploaded",
        "doc_type": None,
        "error": None,
    }
    file_id = UUID(uploaded["id"])
    assert processed_file_ids == [file_id]

    async with test_session_factory() as db:
        stored = await db.get(DocumentFile, file_id)
        assert stored is not None
        assert (test_settings.storage_path / stored.storage_key).read_bytes() == b"%PDF-1.4 stub"

    listed = await client.get(
        f"/api/subjects/{subject.id}/files",
        headers=authorized_session.headers,
    )
    assert listed.status_code == 200
    assert listed.json() == [uploaded]


async def test_file_card_is_scoped_and_includes_processing_results(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
) -> None:
    subject = await create_subject(test_session_factory, authorized_session.user.id)
    document = await create_document(test_session_factory, subject.id, status="processed")
    async with test_session_factory() as db:
        stored = await db.get(DocumentFile, document.id)
        assert stored is not None
        stored.doc_type = "lecture"
        stored.summary_text = "Relational database summary"
        stored.summary_key_terms = ["SQL", "transactions"]
        deadline = Deadline(
            file_id=stored.id,
            subject_id=subject.id,
            title="Submit assignment",
            due_date="2026-11-01",
            date_note=None,
            requirements=["PDF report"],
            source_page=2,
            source_quote="Submit by November 1",
            status="detected",
        )
        deadline.related_files.append(stored)
        db.add(deadline)
        await db.commit()

    card = await client.get(
        f"/api/files/{document.id}",
        headers=authorized_session.headers,
    )
    other = await authorized_session_factory("other@example.com", "other-session")
    foreign_card = await client.get(f"/api/files/{document.id}", headers=other.headers)

    assert card.status_code == 200
    payload = card.json()
    assert payload["summary"] == {
        "text": "Relational database summary",
        "key_terms": ["SQL", "transactions"],
    }
    assert payload["deadlines"][0]["title"] == "Submit assignment"
    assert payload["deadlines"][0]["related_files"] == [payload["file"]]
    assert foreign_card.status_code == 404


async def test_reprocess_clears_results_and_dispatches_owned_file(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    authorized_session_factory: AuthorizedSessionFactory,
    test_session_factory: TestSessionFactory,
    processed_file_ids: list[UUID],
) -> None:
    subject = await create_subject(test_session_factory, authorized_session.user.id)
    document = await create_document(test_session_factory, subject.id, status="processed")
    async with test_session_factory() as db:
        stored = await db.get(DocumentFile, document.id)
        assert stored is not None
        stored.doc_type = "lecture"
        stored.error = "old error"
        stored.summary_text = "old summary"
        stored.summary_key_terms = ["old"]
        db.add(
            Deadline(
                file_id=stored.id,
                subject_id=subject.id,
                title="Old deadline",
                due_date=None,
                date_note=None,
                requirements=[],
                source_page=1,
                source_quote="Old quote",
                status="detected",
            )
        )
        await db.commit()

    other = await authorized_session_factory("other@example.com", "other-session")
    foreign_response = await client.post(
        f"/api/files/{document.id}/reprocess",
        headers=other.headers,
    )
    assert foreign_response.status_code == 404
    assert processed_file_ids == []

    response = await client.post(
        f"/api/files/{document.id}/reprocess",
        headers=authorized_session.headers,
    )

    assert response.status_code == 202
    assert response.content == b""
    assert processed_file_ids == [document.id]
    async with test_session_factory() as db:
        refreshed = await db.get(DocumentFile, document.id)
        assert refreshed is not None
        assert refreshed.status == "uploaded"
        assert refreshed.doc_type is None
        assert refreshed.error is None
        assert refreshed.summary_text is None
        assert refreshed.summary_key_terms is None
        deadlines = list(await db.scalars(select(Deadline).where(Deadline.file_id == document.id)))
        assert deadlines == []


async def test_reprocess_keeps_manually_added_deadlines(
    client: AsyncClient,
    authorized_session: AuthorizedSession,
    test_session_factory: TestSessionFactory,
    processed_file_ids: list[UUID],
) -> None:
    subject = await create_subject(test_session_factory, authorized_session.user.id)
    document = await create_document(test_session_factory, subject.id, status="done")
    async with test_session_factory() as db:
        db.add_all(
            [
                Deadline(
                    file_id=document.id,
                    subject_id=subject.id,
                    title="Found by agent",
                    due_date=None,
                    date_note=None,
                    requirements=[],
                    source_page=1,
                    source_quote="Quote",
                    status="undefined",
                ),
                Deadline(
                    file_id=document.id,
                    subject_id=subject.id,
                    title="Added by hand",
                    due_date="2026-11-10",
                    date_note=None,
                    requirements=[],
                    source_page=None,
                    source_quote=None,
                    status="confirmed",
                    is_manual=True,
                ),
            ]
        )
        await db.commit()

    response = await client.post(
        f"/api/files/{document.id}/reprocess",
        headers=authorized_session.headers,
    )

    assert response.status_code == 202
    assert processed_file_ids == [document.id]
    async with test_session_factory() as db:
        titles = list(await db.scalars(select(Deadline.title)))
    assert titles == ["Added by hand"]
