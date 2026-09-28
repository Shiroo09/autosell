"""Fotoğraf + satıcı notlarından platforma özel ilan (başlık, açıklama, kategori,
özellikler) üretir."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Callable

from ..ai.base import LLMProvider, conform
from ..ai.prompts import LISTING_SYSTEM, listing_prompt
from ..ai.schemas import listing_schema
from ..config import PLATFORMS, Settings
from ..images import for_ai
from ..models import Attribute, Draft, PlatformListing, ProductInfo
from ..textutil import (
    apply_title_style,
    clean_whitespace,
    fit_title,
    remove_contact_info,
    sanitize_listing_text,
    similarity,
    strip_emoji,
    unique_preserve,
)
from .rules import PlatformRules, rules_for
from .title import rank_titles

log = logging.getLogger(__name__)
Logger = Callable[[str], None]


def sanitize_title(title: str, rules: PlatformRules, fit: bool = True) -> str:
    title = remove_contact_info(title or "")
    if not rules.use_emoji:
        title = strip_emoji(title)
    title = title.strip().strip("\"'“”‘’«»").replace("\n", " ")
    title = re.sub(r"\s+", " ", title).strip(" -|,;")
    if not title:
        return ""
    title = apply_title_style(title, rules.title_style)
    return fit_title(title, rules.title_max) if fit else title


def prepare_titles(raw_titles: list[str], rules: PlatformRules) -> tuple[list[str], set[str]]:
    """Adayları temizler ve sınıra sığdırır; kısaltılanları ayrıca döner."""
    titles: list[str] = []
    truncated: set[str] = set()
    for raw in raw_titles:
        full = sanitize_title(raw, rules, fit=False)
        if not full:
            continue
        fitted = fit_title(full, rules.title_max)
        if fitted != full:
            truncated.add(fitted)
        titles.append(fitted)
    return titles, truncated


def finalize_description(text: str, rules: PlatformRules, settings: Settings) -> str:
    desc = sanitize_listing_text(text or "", allow_emoji=rules.use_emoji)
    signature = settings.seller.signature.strip()
    if signature and signature not in desc:
        desc = f"{desc}\n\n{signature}" if desc else signature
    if len(desc) > rules.description_max:
        cut = desc[: rules.description_max]
        para = cut.rfind("\n\n")
        desc = cut[:para] if para > rules.description_max * 0.6 else cut[: cut.rfind(" ")]
    return clean_whitespace(desc)


def seller_attributes(settings: Settings) -> list[Attribute]:
    seller = settings.seller
    out = [Attribute(name="Takas", value="Evet" if seller.allow_trade else "Hayır")]
    if seller.seller_type:
        out.insert(0, Attribute(name="Kimden", value=seller.seller_type))
    return out


def merge_attributes(primary: list[Attribute], defaults: list[Attribute]) -> list[Attribute]:
    merged = [a for a in primary if a.name.strip() and a.value.strip()]
    for default in defaults:
        if not any(similarity(default.name, a.name) >= 0.85 for a in merged):
            merged.append(default)
    return merged


def product_from(data: dict[str, Any]) -> ProductInfo:
    return ProductInfo(
        name=data.get("ad", ""),
        brand=data.get("marka", ""),
        model=data.get("model", ""),
        condition=data.get("durum") or "",
        highlights=unique_preserve(data.get("one_cikanlar", [])),
        defects=unique_preserve(data.get("kusurlar", [])),
        included=unique_preserve(data.get("kutu_icerigi", [])),
        keywords=unique_preserve(data.get("anahtar_kelimeler", [])),
        missing_info=unique_preserve(data.get("eksik_bilgiler", [])),
        warnings=unique_preserve(data.get("uyarilar", [])),
    )


def build_platform_listing(
    raw: dict[str, Any], product: ProductInfo, rules: PlatformRules, settings: Settings
) -> PlatformListing:
    candidates, truncated = prepare_titles(raw.get("baslik_adaylari", []), rules)
    if not candidates:
        fallback = product.name or " ".join(x for x in (product.brand, product.model) if x)
        candidates = [sanitize_title(fallback or "İlan", rules)]
    ranked = rank_titles(candidates, product, rules, truncated)
    attributes = [
        Attribute(name=a.get("ad", "").strip(), value=a.get("deger", "").strip())
        for a in raw.get("ozellikler", [])
        if isinstance(a, dict)
    ]
    path = [re.sub(r"\s+", " ", seg).strip(" >/") for seg in raw.get("kategori_yolu", [])]
    return PlatformListing(
        category_path=[seg for seg in path if seg],
        title=ranked[0].text,
        title_candidates=ranked,
        description=finalize_description(raw.get("aciklama", ""), rules, settings),
        attributes=merge_attributes(attributes, seller_attributes(settings)),
    )


def basic_listing(draft: Draft, settings: Settings) -> Draft:
    """Yapay zekâ kullanılamadığında notlardan basit bir taslak oluşturur (elle düzenlemek için)."""
    lines = [ln.strip() for ln in draft.notes.splitlines() if ln.strip()]
    for platform in draft.platforms:
        rules = rules_for(platform, settings)
        title = sanitize_title(lines[0] if lines else "Yeni İlan", rules)
        body = "\n".join(lines[1:] if len(lines) > 1 else lines)
        if settings.seller.delivery_note:
            body = f"{body}\n\n{settings.seller.delivery_note}".strip()
        existing = draft.listings.get(platform)
        draft.listings[platform] = PlatformListing(
            category_path=existing.category_path if existing else [],
            title=title,
            title_candidates=rank_titles([title], draft.product, rules),
            description=finalize_description(body, rules, settings),
            attributes=merge_attributes(existing.attributes if existing else [], seller_attributes(settings)),
            price=existing.price if existing else None,
        )
    return draft


class ListingGenerator:
    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    def generate(self, draft: Draft, photo_paths: list[Path], log_fn: Logger | None = None) -> Draft:
        say = log_fn or (lambda msg: log.info(msg))
        platforms = [p for p in draft.platforms if p in PLATFORMS] or list(PLATFORMS)
        draft.platforms = platforms
        rules = {p: rules_for(p, self.settings) for p in platforms}

        images = []
        if self.provider.supports_images:
            for path in photo_paths[: max(0, self.settings.ai.max_photos)]:
                try:
                    images.append(for_ai(path))
                except OSError as exc:
                    say(f"Fotoğraf okunamadı ({path.name}): {exc}")
        if not images and not draft.notes.strip():
            raise ValueError("Ürünü tanımlamak için en az bir fotoğraf ya da açıklama notu gerekli.")

        schema = listing_schema(platforms)
        prompt = listing_prompt(draft, self.settings, rules.values(), len(images))
        say(f"Yapay zekâ ürünü inceliyor ({self.provider.describe()}, {len(images)} fotoğraf)...")
        raw = self.provider.generate_json(system=LISTING_SYSTEM, prompt=prompt, schema=schema, images=images)
        data = conform(raw, schema)

        product = product_from(data["urun"])
        draft.product = product
        for platform in platforms:
            listing = build_platform_listing(data[platform], product, rules[platform], self.settings)
            previous = draft.listings.get(platform)
            if previous and previous.price is not None:
                listing.price = previous.price
            draft.listings[platform] = listing
            say(f"{rules[platform].display_name}: en iyi başlık → {listing.title} "
                f"(puan {listing.title_candidates[0].score:.0f})")

        cover = data["urun"].get("kapak_fotografi")
        if isinstance(cover, int) and 0 < cover < min(len(images), len(draft.photos)):
            draft.photos.insert(0, draft.photos.pop(cover))
            say(f"Kapak fotoğrafı olarak {cover + 1}. fotoğraf seçildi.")

        draft.generated = True
        draft.ai_model = self.provider.describe()
        draft.last_error = ""
        return draft
