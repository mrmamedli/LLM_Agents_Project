from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmailRequest(ApiModel):
    email: EmailStr


class EmailPassword(EmailRequest):
    password: str = Field(min_length=8)


class EmailVerification(ApiModel):
    token: str = Field(min_length=1)


class SubjectCreate(ApiModel):
    name: str = Field(min_length=1, max_length=255)


class SubjectOut(ApiModel):
    id: UUID
    name: str


class FileOut(ApiModel):
    id: UUID
    subject_id: UUID
    filename: str
    status: str
    doc_type: str | None
    error: str | None


class SummaryOut(ApiModel):
    text: str
    key_terms: list[str]


class DeadlineOut(ApiModel):
    id: UUID
    file_id: UUID
    subject_id: UUID
    title: str
    due_date: str | None
    date_note: str | None
    requirements: list[str]
    source_page: int = Field(ge=1)
    source_quote: str
    status: str
    related_files: list[FileOut]


class FileCard(ApiModel):
    file: FileOut
    summary: SummaryOut | None
    deadlines: list[DeadlineOut]


class DeadlineUpdate(ApiModel):
    due_date: str | None
    status: str


class DeadlineExtraction(ApiModel):
    title: str
    due_date: str | None
    date_note: str | None
    requirements: list[str]
    source_page: int = Field(ge=1)
    source_quote: str


class FileAnalysis(ApiModel):
    doc_type: str
    summary: str
    key_terms: list[str]
    deadlines: list[DeadlineExtraction]
