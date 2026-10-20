from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, Text, Uuid, false
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base, relationship

json_type = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(UTC)


deadline_related_files = Table(
    "deadline_related_files",
    Base.metadata,
    Column("deadline_id", Uuid, ForeignKey("deadlines.id", ondelete="CASCADE"), primary_key=True),
    Column("file_id", Uuid, ForeignKey("files.id", ondelete="CASCADE"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    is_verified: Mapped[bool] = mapped_column(default=False)
    verification_token: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    subjects: Mapped[list[Subject]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="sessions")


class Subject(Base):
    __tablename__ = "subjects"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped[User] = relationship(back_populates="subjects")
    files: Mapped[list[DocumentFile]] = relationship(
        back_populates="subject", cascade="all, delete-orphan"
    )


class DocumentFile(Base):
    __tablename__ = "files"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(512))
    storage_key: Mapped[str] = mapped_column(String(1024), unique=True)
    status: Mapped[str] = mapped_column(String(64), default="uploaded")
    doc_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_key_terms: Mapped[list[str] | None] = mapped_column(json_type, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    subject: Mapped[Subject] = relationship(back_populates="files")
    deadlines: Mapped[list[Deadline]] = relationship(
        back_populates="file",
        cascade="all, delete-orphan",
        foreign_keys="Deadline.file_id",
    )


class Deadline(Base):
    __tablename__ = "deadlines"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("files.id", ondelete="CASCADE"), index=True, nullable=True
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(512))
    due_date: Mapped[str | None] = mapped_column(String(64), nullable=True)
    date_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[list[str]] = mapped_column(json_type, default=list)
    source_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(64))
    is_manual: Mapped[bool] = mapped_column(default=False, server_default=false())

    file: Mapped[DocumentFile | None] = relationship(
        back_populates="deadlines", foreign_keys=[file_id]
    )
    related_files: Mapped[list[DocumentFile]] = relationship(secondary=deadline_related_files)
