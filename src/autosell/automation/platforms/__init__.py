from __future__ import annotations

from pathlib import Path

from ...ai.base import LLMProvider
from ...config import Settings
from ..interaction import Interaction
from .base import PaymentBlocked, PlatformAdapter, PublishCancelled, PublishError, PublishResult
from .letgo import LetgoAdapter
from .sahibinden import SahibindenAdapter

ADAPTERS: dict[str, type[PlatformAdapter]] = {
    "sahibinden": SahibindenAdapter,
    "letgo": LetgoAdapter,
}


def get_adapter(
    platform: str,
    settings: Settings,
    provider: LLMProvider | None,
    interaction: Interaction,
    shots_dir: Path,
) -> PlatformAdapter:
    try:
        cls = ADAPTERS[platform]
    except KeyError as exc:
        raise ValueError(f"Desteklenmeyen platform: {platform}") from exc
    return cls(settings, provider, interaction, shots_dir)


__all__ = [
    "ADAPTERS",
    "PaymentBlocked",
    "PlatformAdapter",
    "PublishCancelled",
    "PublishError",
    "PublishResult",
    "get_adapter",
]
