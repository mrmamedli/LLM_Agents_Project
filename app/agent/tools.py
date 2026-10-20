"""Async-инструменты агента под свагер и ваши модели.

Все инструменты — async def (у вас async SQLAlchemy). LangGraph ToolNode
автоматически вызывает async-версию через `await tool.ainvoke(...)`.

Инструменты создаются ФАБРИКОЙ build_tools(repository, owner_id) и замыкаются
на конкретный репозиторий+владельца — не требуют глобального состояния и не
зависят от внутренних механизмов langgraph для прокидывания контекста.

Состав (по свагеру):
  read_pdf(file_id, pages)            — постранично читает PDF бинарь из S3;
  list_materials(subject_id)          — файлы предмета (по UUID);
  save_summary(file_id, text, key_terms, doc_type)
                                      — сохраняет SummaryOut в поля DocumentFile;
  save_deadline(file_id, subject_id, title, due_date, date_note,
                requirements, source_page, source_quote)
                                      — создаёт Deadline;
  link_materials(deadline_id, file_ids) — добавляет related_files к дедлайну;
  extract_deadlines(page_text, source_page, current_date)
                                      — constrained decoding через DeadlineExtraction;
  analyze_file(file_id)               — полный анализ: constrained decoding по FileAnalysis,
                                         сам сохраняет конспект и дедлайны.
"""

from __future__ import annotations

from langchain_core.tools import BaseTool, tool
from langchain_openai import ChatOpenAI

from .config import get_settings
from .pdf_reader import read_pdf as _read_pdf
from .repository import Repository
from .schemas import (
    parse_file_analysis,
    response_format_file_analysis,
)

# ---------- Фабрика инструментов ----------


def build_tools(repository: Repository, owner_id: str) -> list[BaseTool]:
    """Создаёт список async-инструментов, замкнутых на repository и owner_id.

    Используется в agent.build_agent_graph() — для каждого прогона агента
    создаётся свой набор инструментов с привязкой к конкретному репозиторию.
    """

    # ---------- read_pdf ----------

    @tool
    async def read_pdf(file_id: str, pages: list[int] | None = None) -> dict:
        """Читает текст из PDF постранично.

        Аргументы:
          file_id — UUID файла;
          pages   — список номеров страниц (1-индексация). None = все страницы.

        Возвращает dict: {file_id, total_pages, requested_pages, returned,
        truncated, pages:[{page, chars, text}]} — либо {file_id, error}.
        """
        # Скачиваем бинарь из S3 через репозиторий.
        pdf_bytes = await repository.get_pdf_bytes(file_id)
        if pdf_bytes is None:
            return {"file_id": file_id, "error": f"PDF для file_id={file_id} не найден в storage"}
        return _read_pdf(file_id, pages, pdf_bytes=pdf_bytes)

    # ---------- list_materials ----------

    @tool
    async def list_materials(subject_id: str) -> dict:
        """Показывает файлы предмета.

        Аргументы:
          subject_id — UUID предмета.

        Возвращает: {subject_id, files:[{id, filename, status, doc_type}], count}.
        """
        files = await repository.list_files_of_subject(subject_id, owner_id)
        return {
            "subject_id": subject_id,
            "files": [
                {"id": f.id, "filename": f.filename, "status": f.status, "doc_type": f.doc_type}
                for f in files
            ],
            "count": len(files),
        }

    # ---------- save_summary ----------

    @tool
    async def save_summary(
        file_id: str, text: str, key_terms: list[str], doc_type: str | None = None
    ) -> dict:
        """Сохраняет конспект в поля файла (summary_text, summary_key_terms)
        и опционально обновляет doc_type.

        Аргументы:
          file_id   — UUID файла;
          text      — текст конспекта;
          key_terms — список ключевых терминов;
          doc_type  — 'lecture' | 'lab_assignment' | 'seminar' | 'other' (опционально).

        Возвращает: {file_id, saved: true}.
        """
        await repository.save_summary(file_id, text, key_terms)
        if doc_type:
            f = await repository.get_file(file_id)
            if f:
                await repository.set_file_status(file_id, f.status, doc_type=doc_type)
        return {"file_id": file_id, "saved": True}

    # ---------- save_deadline ----------

    @tool
    async def save_deadline(
        file_id: str,
        subject_id: str,
        title: str,
        due_date: str | None,
        date_note: str | None,
        requirements: list[str],
        source_page: int,
        source_quote: str,
    ) -> dict:
        """Создаёт дедлайн (модель Deadline) с привязкой к файлу и предмету.

        Аргументы (строго по свагеру, DeadlineExtraction):
          file_id      — UUID файла-источника;
          subject_id   — UUID предмета;
          title        — название задания;
          due_date     — ISO 'YYYY-MM-DD' или null;
          date_note    — исходная формулировка срока из PDF;
          requirements — список требований;
          source_page  — номер страницы PDF (>=1, обязательный);
          source_quote — дословная цитата из PDF.

        Возвращает: {id, saved: true} — UUID созданного дедлайна.
        """
        f = await repository.get_file(file_id)
        if f is None:
            return {"error": f"file_id={file_id} не найден"}
        deadline_id = await repository.save_deadline(
            file_id=file_id,
            subject_id=subject_id,
            owner_id=owner_id,
            title=title,
            due_date=due_date,
            date_note=date_note,
            requirements=requirements,
            source_page=source_page,
            source_quote=source_quote,
        )
        return {"id": deadline_id, "saved": True}

    # ---------- link_materials ----------

    @tool
    async def link_materials(deadline_id: str, file_ids: list[str]) -> dict:
        """Добавляет файлы в related_files дедлайна (M2M).

        Аргументы:
          deadline_id — UUID дедлайна;
          file_ids    — список UUID файлов (лекции, конспекты по теме задания).

        Возвращает: {deadline_id, linked: true}.
        """
        d = await repository.get_deadline(deadline_id)
        if d is None:
            return {"error": f"deadline_id={deadline_id} не найден"}
        await repository.link_related_files(deadline_id, owner_id, file_ids)
        return {"deadline_id": deadline_id, "linked": True}

    # ---------- extract_deadlines ----------

    @tool
    async def extract_deadlines(
        page_text: str, source_page: int, current_date: str | None = None
    ) -> dict:
        """Извлекает дедлайны из текста страницы через constrained decoding.

        Делает отдельный LLM-вызов с response_format={'type':'json_schema',
        'json_schema':{...,'strict':true}} по схеме DeadlineExtraction (лекция 03).

        Возвращает: {deadlines:[DeadlineExtraction], count}.
        """
        return await _llm_extract_deadlines(page_text, source_page, current_date)

    # ---------- analyze_file ----------

    @tool
    async def analyze_file(file_id: str) -> dict:
        """Делает полный анализ файла через один constrained-decoding LLM-вызов.

        Внутренне:
          1. Через репозиторий скачивает PDF бинарь из S3.
          2. LLM-вызов с response_format=json_schema(strict=true) по схеме FileAnalysis.
          3. Сохраняет конспект в поля файла (summary_text, summary_key_terms).
          4. Для каждого DeadlineExtraction — создаёт Deadline.
          5. Обновляет doc_type и переводит файл в 'processed'.

        Возвращает: {doc_type, summary, key_terms, deadlines[]}.
        """
        settings = get_settings()
        f = await repository.get_file(file_id)
        if f is None:
            return {"error": f"file_id={file_id} не найден"}

        pdf_bytes = await repository.get_pdf_bytes(file_id)
        if pdf_bytes is None:
            return {"error": f"PDF бинарь для file_id={file_id} не найден в storage"}

        pdf_data = _read_pdf(file_id, None, pdf_bytes=pdf_bytes)
        if "error" in pdf_data:
            return pdf_data

        pages_text = "\n\n".join(
            f"=== СТРАНИЦА {p['page']} ===\n{p['text']}" for p in pdf_data["pages"]
        )

        llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.api_key,
            base_url=settings.base_url,
            temperature=0,
        )
        sys = (
            "Ты анализируешь учебный PDF и возвращаешь результат строго по схеме FileAnalysis.\n"
            "1. Определи doc_type: 'lecture' | 'lab_assignment' | 'seminar' | 'other'.\n"
            "2. Напиши summary — связный конспект (5–15 предложений).\n"
            "3. Выдели key_terms — список ключевых терминов (5–15 шт).\n"
            "4. Извлеки deadlines[] — все упоминания сроков сдачи.\n"
            "   Для каждого дедлайна:\n"
            "     - title: название задания;\n"
            "     - due_date: ISO 'YYYY-MM-DD' или null, если дату вычислить нельзя;\n"
            "     - date_note: исходная формулировка срока из PDF;\n"
            "     - requirements: список требований;\n"
            "     - source_page: номер страницы (из разметки === СТРАНИЦА N ===);\n"
            "     - source_quote: дословная цитата предложения со сроком.\n"
            f"Текущая дата: {settings.now_iso()} (таймзона {settings.tz_name}).\n"
            "Если дедлайнов в PDF нет — верни пустой массив deadlines."
        )
        resp = await llm.ainvoke(
            [
                {"role": "system", "content": sys},
                {"role": "user", "content": pages_text[:24000]},
            ],
            response_format=response_format_file_analysis(),
        )
        try:
            analysis = parse_file_analysis(resp.content)
        except Exception as e:
            return {
                "error": f"Не удалось распарсить FileAnalysis: {e}",
                "raw": str(resp.content)[:500],
            }

        # Сохраняем конспект в поля файла.
        await repository.save_summary(file_id, analysis.summary, analysis.key_terms)

        # Создаём дедлайны.
        saved_deadlines = []
        for d in analysis.deadlines:
            # source_page обязателен в вашей схеме — гарантируем значение.
            sp = d.source_page if d.source_page is not None else 1
            deadline_id = await repository.save_deadline(
                file_id=file_id,
                subject_id=f.subject_id,
                owner_id=owner_id,
                title=d.title,
                due_date=d.due_date,
                date_note=d.date_note,
                requirements=d.requirements,
                source_page=sp,
                source_quote=d.source_quote,
            )
            saved_deadlines.append({"id": deadline_id, **d.model_dump()})

        # Обновляем doc_type и статус файла.
        await repository.set_file_status(file_id, "processed", doc_type=analysis.doc_type)

        return {
            "doc_type": analysis.doc_type,
            "summary": analysis.summary,
            "key_terms": analysis.key_terms,
            "deadlines": saved_deadlines,
        }

    return [
        read_pdf,
        list_materials,
        save_summary,
        save_deadline,
        link_materials,
        extract_deadlines,
        analyze_file,
    ]


# ---------- LLM-вызов для extract_deadlines ----------


async def _llm_extract_deadlines(
    page_text: str, source_page: int | None, current_date: str | None
) -> dict:
    settings = get_settings()
    llm = ChatOpenAI(
        model=settings.model_name,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=0,
    )
    sys = (
        "Ты извлекаешь дедлайны учебных заданий из текста. "
        "Если на странице нет дедлайнов — верни пустой список deadlines. "
        "Если дата указана относительно ('в следующую пятницу', 'через неделю') — "
        "вычисли абсолютную ISO-дату на основе текущей даты и обязательно сохрани "
        "исходную формулировку в date_note. "
        f"Текущая дата: {current_date or settings.now_iso()}. "
        "Если дату вычислить нельзя — due_date=null, date_note=исходная формулировка. "
        "В source_quote помести дословную цитату предложения со сроком."
    )
    resp = await llm.ainvoke(
        [
            {"role": "system", "content": sys},
            {"role": "user", "content": page_text[:6000]},
        ],
        response_format=response_format_file_analysis(),
    )
    try:
        analysis = parse_file_analysis(resp.content)
    except Exception as e:
        return {
            "error": f"Не удалось распарсить constrained decoding: {e}",
            "raw": str(resp.content)[:500],
        }

    out = []
    for d in analysis.deadlines:
        if source_page is not None and d.source_page is None:
            d.source_page = source_page
        out.append(d.model_dump())
    return {"deadlines": out, "count": len(out)}
