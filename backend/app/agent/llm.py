"""Клиент LLM в формате OpenAI (OpenRouter, YandexGPT, DeepSeek, vLLM, Ollama — что угодно совместимое).

Если LLM не настроена или не ответила, агент работает на правилах: весь путь до покупки от модели не зависит.
"""

import contextvars
import json
import logging
import os
import re
import time
from contextlib import contextmanager
from typing import Any

import httpx

log = logging.getLogger("llm")


class LlmUnavailable(Exception):
    pass


def settings() -> dict:
    return {
        "base_url": os.getenv("LLM_BASE_URL", "").rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "timeout": float(os.getenv("LLM_TIMEOUT_SECONDS", "30")),
        "narrate": os.getenv("LLM_NARRATE", "true").lower() != "false",
    }


_rules_only = contextvars.ContextVar("llm_rules_only", default=False)


@contextmanager
def rules_only():
    """Внутри блока агент работает на правилах, даже если LLM настроена: засев тестовых аккаунтов на старте."""
    token = _rules_only.set(True)
    try:
        yield
    finally:
        _rules_only.reset(token)


def enabled() -> bool:
    s = settings()
    return not _rules_only.get() and bool(s["base_url"] and s["model"])


def status() -> dict:
    s = settings()
    return {"enabled": enabled(), "model": s["model"] if enabled() else None, "mode": "llm" if enabled() else "rules"}


def chat(messages: list[dict[str, str]], *, json_mode: bool = False, max_tokens: int = 700, temperature: float = 0.2) -> str:
    s = settings()
    if not enabled():
        raise LlmUnavailable("LLM не настроена")
    headers = {"Authorization": f"Bearer {s['api_key']}"} if s["api_key"] else {}
    if "qwen3" in s["model"].lower() and "instruct" not in s["model"].lower() and messages and messages[-1]["role"] == "user":
        # у Qwen3 по умолчанию включены «размышления» — на CPU это лишние сотни токенов
        messages = messages[:-1] + [messages[-1] | {"content": messages[-1]["content"] + "\n/no_think"}]
    payload: dict[str, Any] = {"model": s["model"], "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    started = time.perf_counter()
    try:
        response = httpx.post(f"{s['base_url']}/chat/completions", json=payload, headers=headers, timeout=s["timeout"])
        if response.status_code == 400 and json_mode:
            # не все совместимые API знают response_format — пробуем без него
            payload.pop("response_format")
            response = httpx.post(f"{s['base_url']}/chat/completions", json=payload, headers=headers, timeout=s["timeout"])
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as error:
        log.warning("LLM недоступна: %s", error.__class__.__name__)
        raise LlmUnavailable(f"Модель недоступна: {error.__class__.__name__}") from None
    log.info("LLM ответила за %.1f с", time.perf_counter() - started)
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()


def extract_json(text: str) -> dict[str, Any]:
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("нет JSON в ответе")
    return json.loads(text[start : end + 1])
