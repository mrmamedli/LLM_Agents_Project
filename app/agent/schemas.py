"""Структурированный вывод агента (лекция 03 — constrained decoding).

По свагеру используются две внутренние схемы:

  DeadlineExtraction — один извлечённый дедлайн (результат работы агента):
    title         : str
    due_date      : str | null     — ISO 'YYYY-MM-DD' или null, если дату вычислить нельзя
    date_note     : str | null     — исходная формулировка из PDF ('в следующую пятницу')
    requirements  : list[str]
    source_page   : int (>=1)      — номер страницы PDF
    source_quote  : str            — дословная цитата из PDF

  FileAnalysis — результат анализа всего файла:
    doc_type   : str               — 'lecture' | 'lab_assignment' | 'seminar' | 'other'
    summary    : str               — текст конспекта
    key_terms  : list[str]
    deadlines  : list[DeadlineExtraction]

Реализация: один LLM-вызов с response_format={'type':'json_schema','json_schema':{
  'name':'FileAnalysis','schema':FILE_ANALYSIS_SCHEMA,'strict':true}}.
Модель ограничена грамматикой на этапе токенизации — невалидный JSON физически невозможен.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------- Pydantic-модели (для валидации в Python) ----------

class DeadlineExtraction(BaseModel):
    """Один извлечённый дедлайн — внутренняя структура по свагеру."""
    title: str = Field(..., description="Краткое название задания")
    due_date: Optional[str] = Field(
        None, description="ISO-дата 'YYYY-MM-DD' или null, если дату вычислить нельзя"
    )
    date_note: Optional[str] = Field(
        None, description="Исходная формулировка срока из PDF ('в следующую пятницу, 23:59')"
    )
    requirements: list[str] = Field(
        default_factory=list, description="Список требований к работе"
    )
    source_page: int = Field(
        ..., description="Номер страницы PDF (1-индексация)", ge=1
    )
    source_quote: str = Field(
        "", description="Дословная цитата из PDF, из которой извлечён дедлайн"
    )


class FileAnalysis(BaseModel):
    """Полный результат анализа файла — внутренняя структура по свагеру."""
    doc_type: str = Field(
        ..., description="Тип документа: 'lecture' | 'lab_assignment' | 'seminar' | 'other'"
    )
    summary: str = Field(..., description="Текст конспекта")
    key_terms: list[str] = Field(default_factory=list, description="Ключевые термины")
    deadlines: list[DeadlineExtraction] = Field(
        default_factory=list, description="Извлечённые дедлайны"
    )


# ---------- Строгая JSON-схема для response_format ----------

# OpenAI strict-mode требует: все поля required, дополнительные поля запрещены,
# optional поля — через union с null. Никаких $ref/oneOf внутри.
DEADLINE_EXTRACTION_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title":        {"type": "string"},
        "due_date":     {"type": ["string", "null"]},
        "date_note":    {"type": ["string", "null"]},
        "requirements": {"type": "array", "items": {"type": "string"}},
        "source_page":  {"type": "integer"},
        "source_quote": {"type": "string"},
    },
    "required": ["title", "due_date", "date_note", "requirements", "source_page", "source_quote"],
    "additionalProperties": False,
}

FILE_ANALYSIS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "doc_type":  {"type": "string",
                      "description": "Тип документа: 'lecture', 'lab_assignment', 'seminar', 'other'"},
        "summary":   {"type": "string"},
        "key_terms": {"type": "array", "items": {"type": "string"}},
        "deadlines": {"type": "array", "items": DEADLINE_EXTRACTION_SCHEMA},
    },
    "required": ["doc_type", "summary", "key_terms", "deadlines"],
    "additionalProperties": False,
}


def response_format_file_analysis() -> dict:
    """Готовый response_format для ChatOpenAI.invoke (constrained decoding)."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "FileAnalysis",
            "schema": FILE_ANALYSIS_SCHEMA,
            "strict": True,
        },
    }


def parse_file_analysis(raw: str | dict) -> FileAnalysis:
    """Парсит ответ модели в FileAnalysis, валидируя через Pydantic."""
    if isinstance(raw, str):
        import json as _json
        raw = _json.loads(raw)
    return FileAnalysis.model_validate(raw)
