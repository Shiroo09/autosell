"""Yapay zekâ ile fırsat değerlendirmesi (isteğe bağlı web araştırmasıyla)."""

from __future__ import annotations

from typing import Any

from ..ai.base import LLMProvider, conform
from ..ai.prompts import DEAL_SYSTEM, DEAL_WEB_RESEARCH
from ..ai.schemas import deal_eval_schema
from ..config import MarketSettings
from ..models import Deal, MarketEstimate, MarketListing
from ..textutil import format_price


def build_deal_prompt(
    listing: MarketListing, estimate: MarketEstimate, deal: Deal, market: MarketSettings
) -> str:
    details = listing.details or {}
    lines = [
        "Değerlendirilecek ilan:",
        f"- Başlık: {listing.title}",
        f"- Fiyat: {format_price(listing.price, listing.currency)}",
        f"- Konum: {listing.location or '-'} | Tarih: {listing.date_text or '-'} | Platform: {listing.platform}",
    ]
    if listing.price_drop:
        lines.append(f"- Fiyat geçmişi: {format_price(listing.prev_price)} → {format_price(listing.price)}")
    if details.get("attributes"):
        lines.append("- Özellikler: " + "; ".join(f"{k}: {v}" for k, v in list(details["attributes"].items())[:25]))
    if details.get("description"):
        lines.append("- Açıklama: " + details["description"][:1500])
    lines += [
        "",
        f"İstatistik (benzerlik ağırlıklı, {estimate.n} emsal): medyan {format_price(estimate.median)}, "
        f"alt çeyrek {format_price(estimate.p25)}, üst çeyrek {format_price(estimate.p75)}, "
        f"en düşük {format_price(estimate.low)}, en yüksek {format_price(estimate.high)}",
        "Emsal ilanlar (benzerlik puanıyla):",
    ]
    lines += [f"- {c.title} — {format_price(c.price)} (benzerlik {c.similarity:.2f})" for c in estimate.comps]
    lines += [
        "",
        "Alıcının maliyet varsayımları:",
        f"- Alırken beklenen pazarlık indirimi: %{market.negotiation_pct:g}",
        f"- Satışta komisyon: %{market.commission_pct:g}, sabit masraf: {format_price(market.fixed_cost)}",
        f"- İstatistiksel hesap: tahmini net kâr {format_price(deal.est_profit)} (%{deal.margin_pct or 0:.0f})",
        "",
        "Bu ilanın al-sat için gerçekten kârlı bir fırsat olup olmadığını değerlendir.",
    ]
    return "\n".join(lines)


def ai_review(
    provider: LLMProvider,
    listing: MarketListing,
    estimate: MarketEstimate,
    deal: Deal,
    market: MarketSettings,
    web_research: bool = False,
) -> dict[str, Any]:
    schema = deal_eval_schema()
    use_web = web_research and provider.supports_web_search
    system = DEAL_SYSTEM + (DEAL_WEB_RESEARCH if use_web else "")
    raw = provider.generate_json(
        system=system,
        prompt=build_deal_prompt(listing, estimate, deal, market),
        schema=schema,
        web_search=use_web,
        max_tokens=12000,
    )
    return conform(raw, schema)
