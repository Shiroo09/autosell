"""Platform yazım kuralları (karakter sınırları, emoji, başlık biçimi)."""

from __future__ import annotations

from dataclasses import dataclass

from ..config import PLATFORM_NAMES, Settings


@dataclass(frozen=True)
class PlatformRules:
    platform: str
    display_name: str
    title_max: int
    description_max: int
    use_emoji: bool
    title_style: str
    title_min: int = 12


def rules_for(platform: str, settings: Settings) -> PlatformRules:
    ps = settings.platform(platform)
    return PlatformRules(
        platform=platform,
        display_name=PLATFORM_NAMES.get(platform, platform),
        title_max=max(20, ps.title_max),
        description_max=max(200, ps.description_max),
        use_emoji=ps.use_emoji,
        title_style=settings.writing.title_style,
    )
