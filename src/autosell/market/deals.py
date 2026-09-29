"""Al-sat fırsat puanlaması: kâr, marj, güven ve risk işaretleri."""

from __future__ import annotations

import re

from ..config import MarketSettings
from ..models import Deal, MarketEstimate, MarketListing, RiskFlag, Watch
from ..textutil import format_price, normalize

RISK_RULES: list[tuple[str, tuple[str, ...], str]] = [
    ("yuksek", ("kapora", "kaparo", "on odeme", "once odeme", "odemeyi once", "havale ile", "eft ile",
                "kargo ucreti once", "gonderimden once odeme"), "Kapora/ön ödeme isteği: dolandırıcılık riski"),
    ("yuksek", ("icloud", "hesap kilidi", "kilitli", "bloke", "bloklu", "kilidi acilamadi"),
     "Hesap/iCloud kilidi ya da bloke olabilir"),
    ("yuksek", ("kayitsiz", "kayit disi", "imei kayitsiz", "yurt disi", "yurtdisi", "e devlet kaydi yok",
                "btk kaydi yok", "kayit yaptirilmamis"), "Kayıt dışı / yurt dışı cihaz olabilir (IMEI)"),
    ("yuksek", ("replika", "cakma", "muadil", "a kalite", "birebir kopya", "kopya urun", "master copy"),
     "Orijinal olmayabilir"),
    ("orta", ("arizali", "hasarli", "calismiyor", "parca olarak", "parcalik", "ekran kirik", "kirik ekran",
              "sorunlu", "acilmiyor", "sarj olmuyor", "anakart"), "Arıza/hasar belirtilmiş"),
    ("orta", ("agir hasar", "pert", "hurda", "cekme belgeli", "sel hasarli"), "Ağır hasar kaydı olabilir"),
    ("dusuk", ("degisen", "boyali", "tramer", "lokal boya"), "Değişen/boya/tramer kaydı olabilir"),
    ("dusuk", ("cizik", "catlak", "kutusuz", "faturasiz", "garantisiz", "pil sagligi dusuk"),
     "Kozmetik kusur ya da eksik belge"),
]
_LEVEL_PENALTY = {"yuksek": 18.0, "orta": 8.0, "dusuk": 3.0}


_NEGATIONS = re.compile(r"^(?:\s*\w+){0,2}?\s+(?:yok|yoktur|degil|degildir|bulunmuyor|bulunmamaktadir)\b")


def mentions(text: str, word: str) -> bool:
    """Kelime (ve ekli halleri) geçiyor mu? "-sız/-suz" ekli ya da "yok/değil" ile
    olumsuzlanan kullanımlar sayılmaz ("değişensiz", "hasar kaydı yok")."""
    for m in re.finditer(rf"(?:^| ){re.escape(word)}(\w*)", text):
        suffix = m.group(1)
        if suffix.startswith(("siz", "suz")):
            continue
        if _NEGATIONS.match(text[m.end():m.end() + 30]):
            continue
        return True
    return False


def detect_risks(listing: MarketListing, estimate: MarketEstimate) -> list[RiskFlag]:
    details = listing.details or {}
    text = normalize(
        " ".join([listing.title, details.get("description", ""), " ".join(details.get("attributes", {}).values())])
    )
    flags: list[RiskFlag] = []
    for level, words, message in RISK_RULES:
        if any(mentions(text, w) for w in words):
            flags.append(RiskFlag(level=level, text=message))  # type: ignore[arg-type]
    if estimate.median and listing.price:
        ratio = listing.price / estimate.median
        if ratio < 0.5:
            flags.append(RiskFlag(level="yuksek", text="Fiyat piyasanın yarısının altında: dolandırıcılık ya da gizli kusur riski"))
        elif ratio < 0.65:
            flags.append(RiskFlag(level="orta", text="Fiyat piyasanın çok altında; ilanı dikkatle inceleyin"))
    return flags


def evaluate_deal(
    listing: MarketListing,
    estimate: MarketEstimate,
    market: MarketSettings,
    watch: Watch | None = None,
) -> Deal:
    min_profit = watch.min_profit if watch else 1000.0
    min_margin = watch.min_margin_pct if watch else 12.0
    deal = Deal(
        listing_id=listing.id,
        watch_id=watch.id if watch else None,
        est_value=estimate.median,
        resale_price=estimate.resale,
        confidence=estimate.confidence,
        comps_count=estimate.n,
        comps=estimate.comps,
    )
    if not listing.price or not estimate.resale or estimate.n == 0:
        deal.reasons = ["Yeterli emsal ilan yok; piyasa değeri hesaplanamadı."]
        return deal

    buy = listing.price * (1 - market.negotiation_pct / 100)
    net_resale = estimate.resale * (1 - market.commission_pct / 100) - market.fixed_cost
    profit = net_resale - buy
    margin = profit / buy * 100 if buy > 0 else 0.0
    risks = detect_risks(listing, estimate)

    score = 0.0
    score += max(0.0, min(margin, 60.0)) / 60.0 * 45.0
    score += max(0.0, min(profit / max(min_profit * 3, 1.0), 1.0)) * 25.0
    score += estimate.confidence * 20.0
    reasons = [
        f"Piyasa medyanı {format_price(estimate.median)} ({estimate.n} emsal, güven %{round(estimate.confidence * 100)})",
        f"Hedef satış {format_price(estimate.resale)} → tahmini net kâr {format_price(profit)} (%{margin:.0f})",
    ]
    if listing.seen_count <= 1:
        score += 5
        reasons.append("Yeni düşen ilan")
    if listing.price_drop:
        score += 5
        reasons.append(f"Fiyatı düştü: {format_price(listing.prev_price)} → {format_price(listing.price)}")
    score -= sum(_LEVEL_PENALTY[f.level] for f in risks)

    deal.buy_price = round(buy)
    deal.est_profit = round(profit)
    deal.margin_pct = round(margin, 1)
    deal.score = round(max(0.0, min(100.0, score)), 1)
    deal.risk_flags = risks
    deal.reasons = reasons
    deal.is_deal = (
        profit >= min_profit
        and margin >= min_margin
        and estimate.n >= market.min_comps
        and not any(f.level == "yuksek" for f in risks)
    )
    return deal


def apply_ai_review(deal: Deal, review: dict, market: MarketSettings) -> Deal:
    """Yapay zekâ değerlendirmesini fırsata işler."""
    deal.ai = review
    if review.get("firsat_mi") is False:
        deal.is_deal = False
        deal.score = round(deal.score * 0.6, 1)
    elif review.get("firsat_mi") is True:
        deal.score = round(min(100.0, deal.score + 5), 1)
    if review.get("risk_seviyesi") == "yuksek":
        deal.score = round(max(0.0, deal.score - 15), 1)
        deal.is_deal = False
    for text in review.get("riskler") or []:
        if text and not any(text.lower() == f.text.lower() for f in deal.risk_flags):
            deal.risk_flags.append(RiskFlag(level="orta", text=str(text)[:160]))
    return deal
