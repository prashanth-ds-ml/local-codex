from __future__ import annotations

import os

from langchain_ollama import ChatOllama

_LOCAL_BASE_URL = "http://localhost:11434"
_CLOUD_BASE_URL = "https://ollama.com"


def _make_client_kwargs(api_key: str | None = None) -> dict | None:
    api_key = (api_key or os.getenv("OLLAMA_API_KEY", "")).strip()
    if not api_key:
        return None
    return {"headers": {"Authorization": f"Bearer {api_key}"}}


def get_llm(
    model: str,
    temperature: float = 0.2,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
) -> ChatOllama:
    """Return a ChatOllama instance for the given model name."""
    kwargs = {
        "model": model,
        "temperature": temperature,
    }
    if base_url:
        kwargs["base_url"] = base_url
    client_kwargs = _make_client_kwargs(api_key)
    if client_kwargs:
        kwargs["client_kwargs"] = client_kwargs
    return ChatOllama(**kwargs)


def get_local_llm(
    model: str,
    temperature: float = 0.2,
    *,
    base_url: str | None = None,
) -> ChatOllama:
    """Return a client for the local Ollama daemon."""
    return get_llm(model, temperature, base_url=base_url or _LOCAL_BASE_URL)


def get_cloud_llm(
    model: str,
    temperature: float = 0.2,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> ChatOllama:
    """Return a client for Ollama's hosted cloud API."""
    return get_llm(
        model,
        temperature,
        base_url=base_url or _CLOUD_BASE_URL,
        api_key=api_key,
    )


# Legacy aliases kept for any existing call sites
def get_chat_llm(model: str = "qwen2.5-coder:7b", temperature: float = 0.2) -> ChatOllama:
    return get_local_llm(model, temperature)


def get_agent_llm(model: str = "qwen2.5-coder:7b") -> ChatOllama:
    return get_local_llm(model, temperature=0)
