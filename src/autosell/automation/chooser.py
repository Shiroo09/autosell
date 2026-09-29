"""Seçim yardımcısı: önce bulanık eşleştirme, gerekirse yapay zekâ."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from ..ai.base import AIError, LLMProvider, conform
from ..ai.prompts import CATEGORY_SYSTEM, FIELD_CHOICE_SYSTEM
from ..ai.schemas import field_choice_schema, option_pick_schema
from ..textutil import best_match, similarity, tokens
from .driver import Field

log = logging.getLogger(__name__)
MAX_OPTIONS_PER_FIELD = 80


@dataclass
class ChoiceRequest:
    field: Field
    options: list[str]


def _prefilter(options: list[str], context: str, limit: int) -> list[str]:
    if len(options) <= limit:
        return options
    ctx_tokens = set(tokens(context, drop_stopwords=False))
    scored = sorted(
        options,
        key=lambda o: -max([similarity(o, t) for t in ctx_tokens] + [0.0]),
    )
    return scored[:limit]


class Chooser:
    def __init__(self, provider: LLMProvider | None, logger: Callable[[str], None] | None = None):
        self.provider = provider
        self.say = logger or (lambda m: log.info(m))

    def pick_option(
        self,
        options: list[str],
        *,
        hint: str | None,
        context: str,
        purpose: str,
        threshold: float = 0.8,
    ) -> str | None:
        """Seçeneklerden birini seçer (ör. kategori). Bulunamazsa None."""
        if not options:
            return None
        score = 0.0
        if hint:
            idx, score = best_match(hint, options)
            if idx >= 0 and score >= threshold:
                return options[idx]
        if not self.provider:
            if hint:
                idx, score = best_match(hint, options)
                return options[idx] if idx >= 0 and score >= 0.62 else None
            return None
        shown = _prefilter(options, f"{hint or ''} {context}", 150)
        prompt = (
            f"Amaç: {purpose}\n"
            f"Önerilen hedef: {hint or '(yok)'}\n"
            f"Ürün bilgisi:\n{context}\n\n"
            "Bu seviyedeki seçenekler:\n" + "\n".join(f"- {o}" for o in shown)
        )
        try:
            data = conform(
                self.provider.generate_json(
                    system=CATEGORY_SYSTEM, prompt=prompt, schema=option_pick_schema(shown), max_tokens=4000
                ),
                option_pick_schema(shown),
            )
        except AIError as exc:
            self.say(f"Yapay zekâ seçim yapamadı: {exc}")
            return None
        choice = data.get("secim")
        if choice and choice != "YOK" and choice in options:
            self.say(f"Yapay zekâ seçimi: {choice} ({data.get('gerekce', '')[:80]})")
            return choice
        return None

    def choose_fields(self, requests: list[ChoiceRequest], context: str) -> dict[str, str]:
        """Birden çok form alanı için tek çağrıda değer seçer. Dönüş: alan id -> değer."""
        if not self.provider or not requests:
            return {}
        keyed: list[tuple[str, ChoiceRequest, list[str]]] = []
        for i, req in enumerate(requests, 1):
            opts = _prefilter(req.options, f"{req.field.clean_label} {context}", MAX_OPTIONS_PER_FIELD)
            keyed.append((f"f{i}", req, opts))
        schema = field_choice_schema([(key, opts) for key, _, opts in keyed])
        lines = []
        for key, req, opts in keyed:
            f = req.field
            desc = f"{key}: '{f.clean_label}' ({f.kind}{', zorunlu' if f.looks_required else ''})"
            if opts:
                desc += " seçenekler: " + " | ".join(opts)
            if f.error:
                desc += f" — sitenin uyarısı: {f.error}"
            lines.append(desc)
        prompt = f"Ürün ve ilan bilgisi:\n{context}\n\nDoldurulacak alanlar:\n" + "\n".join(lines)
        try:
            raw = self.provider.generate_json(
                system=FIELD_CHOICE_SYSTEM, prompt=prompt, schema=schema, max_tokens=6000
            )
        except AIError as exc:
            self.say(f"Yapay zekâ alan seçimi yapamadı: {exc}")
            return {}
        data = conform(raw, schema)
        out: dict[str, str] = {}
        for key, req, opts in keyed:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                out[req.field.id] = value.strip()
        return out
