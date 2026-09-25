"""
Chat-model factory.

`LLM_PROVIDER` selects the backend; each backend is an optional extra so the core
planning pipeline never depends on an LLM:

| provider | package (extra)          | settings                              |
|----------|--------------------------|---------------------------------------|
| ollama   | langchain-ollama (ollama)| OLLAMA_BASE_URL, OLLAMA_MODEL         |
| gemini   | langchain-google-genai   | GOOGLE_API_KEY, GEMINI_MODEL          |
| openai   | langchain-openai (openai)| OPENAI_API_KEY, OPENAI_MODEL          |

The model must support tool calling; the copilot binds its tools to it.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import httpx

from logistics_tower.config import settings

if TYPE_CHECKING:  # pragma: no cover
    from langchain_core.language_models.chat_models import BaseChatModel

logger = logging.getLogger(__name__)


class LLMNotConfiguredError(RuntimeError):
    """Raised when the selected provider cannot be used (missing package, key or server)."""


def _ollama_reachable(timeout: float = 1.5) -> tuple[bool, list[str]]:
    try:
        r = httpx.get(f"{settings.ollama_base_url.rstrip('/')}/api/tags", timeout=timeout)
        r.raise_for_status()
        return True, [m.get("name", "") for m in r.json().get("models", [])]
    except (httpx.HTTPError, ValueError):
        return False, []


def llm_status() -> dict[str, Any]:
    """Diagnostics for `/copilot/status` and `/agents` (never includes secrets)."""
    provider = settings.llm_provider
    status: dict[str, Any] = {"provider": provider, "available": False, "model": None, "detail": ""}
    if provider == "ollama":
        reachable, models = _ollama_reachable()
        status["model"] = settings.ollama_model
        if not reachable:
            status["detail"] = f"Ollama não respondeu em {settings.ollama_base_url}."
        elif models and settings.ollama_model not in models and f"{settings.ollama_model}:latest" not in models:
            status["detail"] = f"Modelo {settings.ollama_model} não encontrado; instalados: {', '.join(models[:6])}."
        else:
            status["available"] = True
    elif provider == "gemini":
        status["model"] = settings.gemini_model
        status["available"] = bool(settings.google_api_key and settings.google_api_key.get_secret_value())
        status["detail"] = "" if status["available"] else "GOOGLE_API_KEY não configurada."
    elif provider == "openai":
        status["model"] = settings.openai_model
        status["available"] = bool(settings.openai_api_key and settings.openai_api_key.get_secret_value())
        status["detail"] = "" if status["available"] else "OPENAI_API_KEY não configurada."
    return status


def _build_model(provider: str, temperature: float) -> BaseChatModel:
    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:  # pragma: no cover - depends on extras
            raise LLMNotConfiguredError("Instale o extra: pip install -e '.[ollama]'") from exc
        return ChatOllama(model=settings.ollama_model, base_url=settings.ollama_base_url, temperature=temperature)

    if provider == "gemini":
        if not (settings.google_api_key and settings.google_api_key.get_secret_value()):
            raise LLMNotConfiguredError("GOOGLE_API_KEY não configurada para o provedor gemini.")
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover
            raise LLMNotConfiguredError("Instale o extra: pip install -e '.[gcp]'") from exc
        return ChatGoogleGenerativeAI(
            model=settings.gemini_model,
            google_api_key=settings.google_api_key.get_secret_value(),
            temperature=temperature,
        )

    if provider == "openai":
        if not (settings.openai_api_key and settings.openai_api_key.get_secret_value()):
            raise LLMNotConfiguredError("OPENAI_API_KEY não configurada para o provedor openai.")
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:  # pragma: no cover
            raise LLMNotConfiguredError("Instale o extra: pip install -e '.[openai]'") from exc
        return ChatOpenAI(model=settings.openai_model, api_key=settings.openai_api_key, temperature=temperature)

    raise LLMNotConfiguredError(f"Provedor de LLM desconhecido: {provider}")


@lru_cache(maxsize=4)
def get_chat_model(provider: str | None = None, temperature: float = 0.0) -> BaseChatModel:
    """Return a (cached) chat model for the configured or given provider."""
    chosen = provider or settings.llm_provider
    status = llm_status() if chosen == settings.llm_provider else {"available": True, "detail": ""}
    if not status["available"]:
        raise LLMNotConfiguredError(status["detail"] or f"Provedor {chosen} indisponível.")
    model = _build_model(chosen, temperature)
    logger.info("LLM provider ready: %s (%s)", chosen, getattr(model, "model", getattr(model, "model_name", "?")))
    return model
