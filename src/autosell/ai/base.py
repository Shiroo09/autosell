"""Yapay zekâ sağlayıcı arayüzü ve ortak yardımcılar."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Sequence


@dataclass(frozen=True)
class ImageInput:
    media_type: str
    data_b64: str


class AIError(RuntimeError):
    """Yapay zekâ çağrısı başarısız oldu."""


class AINotConfigured(AIError):
    """API anahtarı/model ayarı eksik ya da geçersiz."""


class AIRefusal(AIError):
    """Model isteği güvenlik gerekçesiyle reddetti."""


class LLMProvider(ABC):
    name: str = "llm"
    model: str = ""
    supports_images: bool = True
    supports_web_search: bool = False

    @abstractmethod
    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        images: Sequence[ImageInput] = (),
        web_search: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        """Verilen JSON şemasına uyan bir nesne üretir."""

    def describe(self) -> str:
        return f"{self.name}:{self.model}"


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_json(text: str) -> dict[str, Any]:
    """Model çıktısından JSON nesnesini çıkarır (kod bloğu / ön-arka metin toleranslı)."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Boş yanıt")
    candidates = [text]
    candidates += [m.group(1).strip() for m in _FENCE_RE.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    for cand in candidates:
        try:
            value = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("Yanıtta geçerli JSON nesnesi bulunamadı")


def conform(value: Any, schema: dict[str, Any]) -> Any:
    """Zayıf modellerin çıktısını şemaya uydurur: eksik alanları varsayılanla doldurur,
    türleri düzeltir. Geçersiz enum değerleri None olur."""
    if "enum" in schema:
        options = schema["enum"]
        if value in options:
            return value
        if isinstance(value, str):
            low = value.strip().casefold()
            for opt in options:
                if isinstance(opt, str) and opt.casefold() == low:
                    return opt
        return None
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            if sub.get("type") == "null" and value is None:
                return None
        for sub in schema["anyOf"]:
            if sub.get("type") != "null":
                return conform(value, sub)
        return None
    kind = schema.get("type")
    if kind == "object":
        value = value if isinstance(value, dict) else {}
        return {key: conform(value.get(key), sub) for key, sub in schema.get("properties", {}).items()}
    if kind == "array":
        if not isinstance(value, list):
            value = [] if value in (None, "") else [value]
        items = schema.get("items", {})
        out = [conform(v, items) for v in value]
        return [v for v in out if v is not None]
    if kind == "string":
        if value is None:
            return ""
        return value if isinstance(value, str) else str(value)
    if kind in ("number", "integer"):
        if isinstance(value, bool) or value in (None, ""):
            return None
        try:
            num = float(str(value).replace(",", ".")) if isinstance(value, str) else float(value)
        except (TypeError, ValueError):
            return None
        return int(num) if kind == "integer" else num
    if kind == "boolean":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().casefold() in ("true", "evet", "yes", "1")
        return bool(value)
    return value
