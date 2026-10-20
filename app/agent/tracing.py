"""Логирование каждого шага цикла tool-calling (Tracing).

Не зависит от БД — пишет в stdout через logging. Если вы хотите сохранять
trace в файл или БД, переопределите функцию `trace()` (например, пишите в
таблицу agent_runs вашего проекта).

Формат записи:
  • какие инструменты вызваны и с какими аргументами;
  • что вернул каждый инструмент (сокращённо);
  • токен-usage LLM на каждой итерации;
  • моменты принятия решений моделью.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

logger = logging.getLogger("agent_study")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def trace(run_id: str, kind: str, payload: dict[str, Any]) -> None:
    """Логирует шаг цикла агента.

    kind — одна из: 'start', 'agent_call', 'tool_call', 'tool_result',
                   'iteration', 'end', 'error'.

    Чтобы сохранять trace в БД — переопределите эту функцию или оберните
    вызовом, который пишет в таблицу agent_runs вашего проекта.
    """
    if kind == "agent_call":
        logger.info(
            "[agent] iter=%s tools=%s tokens=%s",
            payload.get("iteration"),
            payload.get("tool_calls"),
            payload.get("usage"),
        )
    elif kind == "tool_call":
        logger.info("[tool ] → %s(%s)", payload.get("name"), _short(payload.get("args")))
    elif kind == "tool_result":
        logger.info("[tool ] ← %s  %s", payload.get("name"), _short(payload.get("result")))
    elif kind == "iteration":
        logger.info("[iter ] %s/%s", payload.get("iteration"), payload.get("max"))
    elif kind == "end":
        logger.info(
            "[done ] tool_calls=%s deadlines=%s summary=%s status=%s",
            payload.get("tool_calls"),
            payload.get("deadlines"),
            payload.get("summary"),
            payload.get("status"),
        )
    elif kind == "error":
        logger.error("[err  ] %s", payload.get("message"))
    elif kind == "start":
        logger.info(
            "[start] run_id=%s file_id=%s owner=%s",
            run_id,
            payload.get("file_id"),
            payload.get("owner_id"),
        )


def _short(obj: Any, limit: int = 200) -> str:
    s = repr(obj)
    return s if len(s) <= limit else s[:limit] + "…"
