"""Ayarlara göre yapay zekâ sağlayıcısı oluşturur."""

from __future__ import annotations

from ..config import DEFAULT_CLAUDE_MODEL, Settings
from .base import LLMProvider


def build_provider(settings: Settings) -> LLMProvider:
    ai = settings.ai
    if ai.provider == "openai":
        from .openai_provider import OpenAICompatProvider

        return OpenAICompatProvider(
            model=ai.openai_model.strip(),
            base_url=ai.openai_base_url.strip(),
            api_key=ai.openai_api_key.strip(),
            vision=ai.openai_vision,
        )
    from .anthropic_provider import AnthropicProvider

    return AnthropicProvider(
        model=ai.claude_model.strip() or DEFAULT_CLAUDE_MODEL,
        effort=ai.claude_effort,
        api_key=ai.claude_api_key.strip(),
        fallback=ai.claude_fallback,
    )
