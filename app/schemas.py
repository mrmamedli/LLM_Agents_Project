from __future__ import annotations

from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    StringConstraints,
    field_validator,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmailRequest(ApiModel):
    email: EmailStr


class EmailPassword(EmailRequest):
    password: str = Field(min_length=8)


class EmailVerification(ApiModel):
    token: str = Field(min_length=1)


class CurrentUserOut(ApiModel):
    id: UUID
    email: EmailStr


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
    file_id: UUID | None
    subject_id: UUID
    title: str
    due_date: str | None
    date_note: str | None
    requirements: list[str]
    source_page: int | None = Field(ge=1)
    source_quote: str | None
    status: str
    is_manual: bool
    related_files: list[FileOut]


class FileCard(ApiModel):
    file: FileOut
    summary: SummaryOut | None
    deadlines: list[DeadlineOut]


class DeadlineUpdate(ApiModel):
    due_date: str | None
    status: str


class DeadlineCreate(ApiModel):
    subject_id: UUID
    file_id: UUID | None = None
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
    due_date: str | None = None
    requirements: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]] = (
        Field(default_factory=list, max_length=50)
    )

    @field_validator("due_date")
    @classmethod
    def due_date_must_be_iso(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            if "T" in value:
                datetime.fromisoformat(value)
            else:
                date.fromisoformat(value)
        except ValueError as error:
            raise ValueError("due_date must be YYYY-MM-DD or YYYY-MM-DDTHH:MM") from error
        return value


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
