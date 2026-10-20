"""Конфигурация агента: переменные окружения, текущая дата и таймзона.

Поддерживает два режима LLM:
  1. Облачный OpenAI-совместимый провайдер (OpenAI, DeepSeek, OpenRouter, Together, vLLM).
  2. Локальная LLM через Ollama (например, qwen2.5:7b) — по умолчанию.

Для Ollama достаточно установить OPENAI_API_KEY=ollama (заглушка, Ollama её не
проверяет) и OPENAI_BASE_URL=http://localhost:11434/v1 — Ollama предоставляет
OpenAI-совместимый endpoint через /v1/chat/completions.

Переменные (см. .env.example):
  OPENAI_API_KEY   — ключ провайдера (для Ollama: любое значение, напр. 'ollama');
  OPENAI_BASE_URL  — base URL: http://localhost:11434/v1 для Ollama;
  MODEL_NAME       — имя модели: qwen2.5:7b, llama3.1:8b, mistral:7b и т.п.;
  TZ               — таймзона для вычисления дат;
  MAX_ITERATIONS   — защита от зацикливания цикла tool-calling;
  USE_STRUCTURED_OUTPUT — использовать response_format=json_schema (strict).
                    True для провайдеров с поддержкой (OpenAI, vLLM).
                    False для Ollama — он пока плохо поддерживает strict JSON Schema,
                    агент использует fallback: просит JSON в промпте и парсит.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo


def _env(key: str, default: str | None = None, *, required: bool = False) -> str:
    val = os.getenv(key, default)
    if required and not val:
        raise RuntimeError(f"Env-переменная {key} не задана. Скопируйте .env.example → .env и заполните.")
    return val  # type: ignore[return-value]


def _env_bool(key: str, default: bool) -> bool:
    return _env(key, str(default)).lower() in ("true", "1", "yes", "on")


@dataclass(frozen=True)
class Settings:
    api_key: str
    base_url: str
    model_name: str
    tz_name: str
    max_iterations: int
    # True → response_format=json_schema(strict=true) для извлечения дедлайнов.
    # False → fallback: просим JSON в системном промпте и парсим ответ.
    # По умолчанию False — безопасно для Ollama/qwen2.5.
    use_structured_output: bool

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.tz_name)

    def now(self) -> datetime:
        """Текущее время в настроенной таймзоне — для системного промпта."""
        return datetime.now(self.tz)

    def now_iso(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def now_human(self) -> str:
        """Человекочитаемая дата+день недели+таймзона для системного промпта."""
        n = self.now()
        return n.strftime("%Y-%m-%d (%A) %H:%M %Z")

    @property
    def is_ollama(self) -> bool:
        """True если базовый URL указывает на локальную Ollama."""
        return "localhost:11434" in self.base_url or "127.0.0.1:11434" in self.base_url


def load_settings() -> Settings:
    """Загружает настройки из окружения. Должна вызываться после dotenv.load_dotenv()."""
    print("load_settings")
    return Settings(
        api_key=_env("OPENAI_API_KEY", required=True),
        # По умолчанию — локальная Ollama.
        base_url=_env("OPENAI_BASE_URL", "http://localhost:11434/v1"),
        # По умолчанию — qwen2.5:7b (хорошо работает с tool-calling и русским).
        model_name=_env("MODEL_NAME", "qwen2.5:latest"),
        tz_name=_env("TZ", "Europe/Moscow"),
        max_iterations=int(_env("MAX_ITERATIONS", "15")),
        # Ollama не поддерживает strict json_schema — по умолчанию False.
        use_structured_output=_env_bool("USE_STRUCTURED_OUTPUT", False),
    )

_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        from dotenv import load_dotenv
        load_dotenv()
        _settings = load_settings()
    return _settings


def reset_settings_cache() -> None:
    """Сбросить кэш настроек (для тестов, меняющих env)."""
    global _settings
    _settings = None