"""Async-агент на LangGraph

Поддерживает облачные LLM (OpenAI/DeepSeek/vLLM) и локальную Ollama
(qwen2.5:7b и др.) — выбирается через OPENAI_BASE_URL и MODEL_NAME в .env.

Для Ollama:
  • OPENAI_API_KEY=ollama (заглушка, Ollama не проверяет ключ);
  • OPENAI_BASE_URL=http://localhost:11434/v1 (OpenAI-совместимый endpoint);
  • MODEL_NAME=qwen2.5:7b (или llama3.1:8b, mistral:7b и т.п.);
  • USE_STRUCTURED_OUTPUT=false (Ollama плохо поддерживает strict JSON Schema).

StateGraph:
  START → agent_node ──tool_calls?──► tool_node ──► agent_node ──► ... ──► END
  Защита от зацикливания: settings.max_iterations.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Optional

from langchain_core.messages import AIMessage, BaseMessage, SystemMessage, ToolMessage
from langchain_core.tools import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict

from . import tracing
from .config import get_settings
from .repository import Repository
from .tools import build_tools
from .tracing import logger


# ---------- State цикла ----------

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    file_id: str               # UUID
    run_id: str
    iteration: int
    tool_calls_total: int


# ---------- Системный промпт ----------

SYSTEM_PROMPT_TEMPLATE = """\
Ты — учебный ассистент. Твоя задача — обработать PDF-файл:
определить тип документа, сделать конспект, извлечь дедлайны (если есть)
и проставить связи с другими материалами предмета.

ТЕКУЩАЯ ДАТА И ВРЕМЯ: {now_human} (таймзона {tz}).
Используй эту дату для разрешения относительных формулировок вроде «в следующую пятницу»,
«через две недели», «к следующему занятию». Если дата в тексте абсолютная — бери как есть.
Если дату вычислить нельзя — due_date=null и в date_note — исходная формулировка.

ВХОДНОЙ ФАЙЛ:
  file_id = {file_id}

ДОСТУПНЫЕ ИНСТРУМЕНТЫ:
  • read_pdf(file_id, pages)             — постранично читает PDF из S3;
  • list_materials(subject_id)           — файлы предмета (по UUID);
  • save_summary(file_id, text, key_terms, doc_type?)
                                         — сохраняет конспект в поля файла
                                           (summary_text + summary_key_terms)
                                           и опционально обновляет doc_type;
  • save_deadline(file_id, subject_id, title, due_date, date_note,
                  requirements, source_page, source_quote)
                                         — создаёт дедлайн (модель Deadline);
  • link_materials(deadline_id, file_ids) — добавляет related_files к дедлайну (M2M);
  • extract_deadlines(page_text, source_page, current_date?)
                                         — извлекает дедлайны со страницы через LLM;
  • analyze_file(file_id)                — ПОЛНЫЙ анализ файла одним вызовом
                                           (LLM возвращает JSON со схемой FileAnalysis):
                                           возвращает {{doc_type, summary, key_terms, deadlines[]}}
                                           и сам сохраняет конспект и дедлайны в БД.

РЕКОМЕНДУЕМЫЙ ПЛАН (но порядок выбираешь ты):
  1. Вызови analyze_file(file_id) — это сделает основную работу: определит doc_type,
     сделает конспект, извлечёт дедлайны, сохранит всё в БД.
  2. Если нужно — дополни результат: вызови read_pdf для проверки отдельных страниц,
     save_deadline для ручной правки, link_materials для связи дедлайна с другими лекциями.
  3. После analyze_file файл считается обработанным. Можешь завершать работу.

ВАЖНО:
  • Не выдумывай даты. Если в тексте даты нет — due_date=null, date_note=исходная формулировка.
  • source_page бери из разметки страниц PDF (=== СТРАНИЦА N ===). Минимум 1.
  • source_quote — дословная цитата предложения со сроком (не пересказ).
  • Останавливайся, как только файл обработан: analyze_file выполнен, при необходимости —
    правки внесены. Финальное сообщение — короткая сводка без вызова инструментов.
"""


def build_system_prompt(file_id: str) -> str:
    s = get_settings()
    return SYSTEM_PROMPT_TEMPLATE.format(
        now_human=s.now_human(),
        tz=s.tz_name,
        file_id=file_id,
    )


# ---------- Создание LLM-клиента ----------

def _make_llm() -> ChatOpenAI:
    """Создаёт ChatOpenAI под Ollama или любой OpenAI-совместимый провайдер.

    Для Ollama: timeout=180 (7B на CPU может думать долго), max_retries=2.
    """
    s = get_settings()
    return ChatOpenAI(
        model=s.model_name,
        api_key=s.api_key,
        base_url=s.base_url,
        temperature=0,
        # Локальная 7B-модель на CPU может отвечать 30-60 сек на запрос.
        timeout=180,
        max_retries=2,
    )


# ---------- Ноды графа (async) ----------

def _make_agent_node(llm_with_tools, max_iterations: int, repository: Repository,
                     owner_id: str, run_id: str):

    async def agent_node(state: AgentState) -> dict:
        iteration = state.get("iteration", 0) + 1
        tracing.trace(run_id, "iteration", {"iteration": iteration, "max": max_iterations})

        if iteration > max_iterations:
            tracing.trace(run_id, "error", {
                "message": f"Превышен лимит итераций ({max_iterations}). Останавливаюсь.",
            })
            await repository.set_file_status(
                state["file_id"], "failed",
                error=f"Превышен лимит итераций ({max_iterations})",
            )
            return {
                "messages": [AIMessage(content=(
                    f"Остановлено: превышен лимит итераций ({max_iterations})."
                ))],
                "iteration": iteration,
            }

        messages = list(state["messages"])
        if not any(isinstance(m, SystemMessage) for m in messages):
            messages.insert(0, SystemMessage(content=build_system_prompt(state["file_id"])))

        # async-вызов LLM (Ollama или облако).
        resp = await llm_with_tools.ainvoke(messages)
        tool_calls = getattr(resp, "tool_calls", None) or []
        usage = getattr(resp, "usage_metadata", None)
        tracing.trace(run_id, "agent_call", {
            "iteration": iteration,
            "tool_calls": [tc.get("name") for tc in tool_calls],
            "usage": usage,
            "content_preview": (resp.content or "")[:300],
            "messages_in_context": len(messages),
        })

        return {"messages": [resp], "iteration": iteration,
                "tool_calls_total": state.get("tool_calls_total", 0) + len(tool_calls)}

    return agent_node


def _make_tool_node_with_tracing(tools: list[BaseTool], run_id: str):
    """Async ToolNode с трейсингом."""

    class _TracingToolNode(ToolNode):
        async def ainvoke(self, state, config=None, **kw):
            last: AIMessage = state["messages"][-1]
            for tc in (last.tool_calls or []):
                tracing.trace(run_id, "tool_call", {
                    "name": tc.get("name"), "args": tc.get("args"), "id": tc.get("id"),
                })

            result = await super().ainvoke(state, config=config, **kw)
            new_msgs = result["messages"] if isinstance(result, dict) else result
            for m in new_msgs:
                if isinstance(m, ToolMessage):
                    content = m.content
                    preview = content[:500] if isinstance(content, str) else str(content)[:500]
                    tracing.trace(run_id, "tool_result", {
                        "name": m.name, "tool_call_id": m.tool_call_id, "result": preview,
                    })
            return result

    return _TracingToolNode(tools)


def should_continue(state: AgentState) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and getattr(last, "tool_calls", None):
        return "tools"
    return END


# ---------- Сборка графа ----------

def build_agent_graph(repository: Repository, owner_id: str, run_id: str,
                      tools: list[BaseTool] | None = None) -> Any:
    """Собирает StateGraph агента с привязкой к конкретному репозиторию."""
    settings = get_settings()
    tools = tools or build_tools(repository, owner_id)

    llm = _make_llm()
    llm_with_tools = llm.bind_tools(tools)

    graph = StateGraph(AgentState)
    graph.add_node("agent", _make_agent_node(llm_with_tools, settings.max_iterations,
                                             repository, owner_id, run_id))
    graph.add_node("tools", _make_tool_node_with_tracing(tools, run_id))
    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")
    return graph.compile()


# ---------- Точка входа: обработать файл ----------

async def process_file(file_id: str, repository: Repository, owner_id: str,
                       run_id: Optional[str] = None) -> dict:
    settings = get_settings()
    run_id = run_id or uuid.uuid4().hex[:12]

    meta = await repository.get_file(file_id)
    if meta is None:
        tracing.trace(run_id, "error", {"message": f"file_id={file_id} не найден"})
        return {"run_id": run_id, "file_id": file_id, "status": "failed",
                "error": "file not found"}
    await repository.set_file_status(file_id, "processing")

    tracing.trace(run_id, "start", {"file_id": file_id, "owner_id": owner_id,
                                     "now": settings.now_iso(),
                                     "model": settings.model_name,
                                     "is_ollama": settings.is_ollama})
    logger.info("=== Запуск агента: run_id=%s file_id=%s model=%s ollama=%s ===",
                run_id, file_id, settings.model_name, settings.is_ollama)

    try:
        graph = build_agent_graph(repository, owner_id, run_id)
        initial: AgentState = {
            "messages": [],
            "file_id": file_id,
            "run_id": run_id,
            "iteration": 0,
            "tool_calls_total": 0,
        }
        final_state = await graph.ainvoke(
            initial,
            config={"recursion_limit": settings.max_iterations * 3 + 5},
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("Agent failed")
        await repository.set_file_status(file_id, "failed", error=str(e))
        tracing.trace(run_id, "error", {"message": str(e)})
        return {"run_id": run_id, "file_id": file_id, "status": "failed",
                "error": str(e)}

    # Если статус остался 'processing' (агент не вызвал analyze_file),
    # помечаем как processed только если есть конспект.
    meta = await repository.get_file(file_id)
    if meta and meta.status == "processing":
        summary = await repository.get_summary(file_id)
        if summary is not None:
            await repository.set_file_status(file_id, "processed")
        else:
            await repository.set_file_status(file_id, "failed",
                                             error="Агент не сохранил конспект")

    meta = await repository.get_file(file_id)
    summary = await repository.get_summary(file_id)
    deadlines = await repository.list_deadlines_of_file(file_id, owner_id) if meta else []

    result = {
        "run_id": run_id,
        "file_id": file_id,
        "status": meta.status if meta else "unknown",
        "iterations": final_state.get("iteration", 0),
        "tool_calls": final_state.get("tool_calls_total", 0),
        "deadlines_saved": len(deadlines),
        "summary_saved": summary is not None,
    }
    tracing.trace(run_id, "end", {
        "tool_calls": result["tool_calls"],
        "deadlines": result["deadlines_saved"],
        "summary": result["summary_saved"],
        "iterations": result["iterations"],
        "status": result["status"],
    })
    return result