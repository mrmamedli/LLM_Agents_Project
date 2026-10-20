"""Постраничное чтение PDF через PyMuPDF (pymupdf).

Чистая утилита — не зависит от storage/БД. Принимает либо путь к PDF напрямую,
либо бинарь в bytes. Используется инструментом read_pdf, который достаёт путь
через Repository (см. tools.py).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import pymupdf  # PyMuPDF

# Лимит символов на страницу — чтобы не раздувать контекст модели.
MAX_CHARS_PER_PAGE = 8000
# Если запросили слишком много страниц — обрезаем и помечаем truncated.
MAX_PAGES_PER_CALL = 20


def _normalize_pages(pages: Iterable[int] | None, total: int) -> list[int]:
    if pages is None:
        return list(range(1, total + 1))
    out: list[int] = []
    for p in pages:
        if not isinstance(p, int):
            try:
                p = int(p)
            except (TypeError, ValueError):
                continue
        if 1 <= p <= total:
            out.append(p)
    return sorted(set(out))


def read_pdf(
    file_id: str,
    pages: Iterable[int] | None = None,
    *,
    pdf_path: Path | None = None,
    pdf_bytes: bytes | None = None,
) -> dict:
    """Читает указанные страницы PDF и возвращает текст постранично.

    Способы получить бинарь (в порядке приоритета):
      1. pdf_path — путь к файлу на диске (Repository.get_pdf_path());
      2. pdf_bytes — бинарь в памяти (если файлы в S3, качаете их в обработчике
         и передаёте сюда).

    Возвращает dict: {file_id, total_pages, requested_pages, returned,
    truncated, pages:[{page, chars, text}]} — либо {file_id, error}.
    """
    if pdf_path is None and pdf_bytes is None:
        return {"file_id": file_id, "error": "Не передан ни pdf_path, ни pdf_bytes"}

    try:
        if pdf_path is not None:
            doc = pymupdf.open(pdf_path)
        else:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    except Exception as e:
        return {"file_id": file_id, "error": f"Не удалось открыть PDF: {e}"}

    total = doc.page_count
    requested = _normalize_pages(pages, total)

    truncated = False
    if len(requested) > MAX_PAGES_PER_CALL:
        requested = requested[:MAX_PAGES_PER_CALL]
        truncated = True

    out_pages = []
    for pn in requested:
        page = doc.load_page(pn - 1)
        text = (page.get_text("text") or "").strip()
        if len(text) > MAX_CHARS_PER_PAGE:
            text = text[:MAX_CHARS_PER_PAGE] + f"\n…[обрезано, всего {len(text)} символов]"
        out_pages.append({"page": pn, "chars": len(text), "text": text})
    doc.close()

    return {
        "file_id": file_id,
        "total_pages": total,
        "requested_pages": requested,
        "returned": len(out_pages),
        "truncated": truncated,
        "pages": out_pages,
    }


def page_count(*, pdf_path: Path | None = None, pdf_bytes: bytes | None = None) -> int | None:
    """Быстро возвращает количество страниц в PDF."""
    try:
        if pdf_path is not None:
            doc = pymupdf.open(pdf_path)
        elif pdf_bytes is not None:
            doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        else:
            return None
        n = doc.page_count
        doc.close()
        return n
    except Exception:
        return None
