"""Fiyat araştırması: emsal ilanlardan piyasa değeri tahmini.

Başlıklar anahtar kelimelere ayrılır (pazarlama kelimeleri atılır, renkler düşük
ağırlık alır) ve kapsama + örtüşme benzerliği hesaplanır; kapasite (GB), sürüm
(Pro/Max/Plus...), model numarası ve aksesuar/parça farkları sert cezalandırılır. Aykırı fiyatlar IQR ile ayıklanır,
benzerlik ağırlıklı medyan ve yüzdelikler hesaplanır.
"""

from __future__ import annotations

import math
import re
from typing import Iterable, Sequence

from ..models import CompRef, MarketEstimate, MarketListing
from ..textutil import tokens

VARIANT_WORDS = frozenset({"pro", "max", "plus", "mini", "ultra", "lite", "fe", "se", "air", "neo", "note", "edge",
                           "slim", "digital", "dijital"})
ACCESSORY_WORDS = frozenset({
    "kilif", "kapak", "sarj", "kablo", "koruyucu", "kulaklik", "adaptor", "cam", "batarya", "parca", "kasa",
    "stand", "tutucu", "aparat", "anakart", "ekran", "lens", "kordon", "kayis", "aksesuar", "yedek", "kutusu",
})
_STORAGE = re.compile(r"^\d+(?:gb|tb)$")
_YEAR = re.compile(r"^(19[89]\d|20[0-4]\d)$")


def _token_set(title: str) -> set[str]:
    return set(tokens(title))


# Ürün kimliğini belirlemeyen, fiyatı az etkileyen kelimeler (renk vb.) düşük ağırlık alır.
LOW_WEIGHT_WORDS = frozenset({
    "siyah", "beyaz", "mavi", "kirmizi", "yesil", "pembe", "mor", "gri", "gumus", "altin", "gold", "silver",
    "lacivert", "sari", "turuncu", "kahverengi", "bej", "krem", "uzay", "grisi", "gece", "yarisi", "yildiz",
    "isigi", "grafit", "rose", "titanyum", "renk", "renkli", "apple", "telefon", "telefonu", "cep", "akilli",
    "adet", "pil", "saglik", "sagligi", "kutu", "urun",
})


def _weight(token: str) -> float:
    return 0.15 if token in LOW_WEIGHT_WORDS else 1.0


def title_similarity(a: str, b: str) -> float:
    """Hedef başlık (a) ile emsal başlık (b) arasında 0..1 ürün kimliği benzerliği."""
    ta, tb = _token_set(a), _token_set(b)
    if not ta or not tb:
        return 0.0
    inter = sum(_weight(t) for t in ta & tb)
    # hedefteki kelimelerin ne kadarı emsalde var (kapsama) + genel örtüşme
    cover = inter / sum(_weight(t) for t in ta)
    jacc = inter / sum(_weight(t) for t in ta | tb)
    score = 0.6 * cover + 0.4 * jacc

    sa, sb = {t for t in ta if _STORAGE.match(t)}, {t for t in tb if _STORAGE.match(t)}
    if sa and sb and sa.isdisjoint(sb):
        score *= 0.35
    va, vb = ta & VARIANT_WORDS, tb & VARIANT_WORDS
    if va != vb:
        score *= 0.5
    na = {t for t in ta if t.isdigit() and not _YEAR.match(t) and len(t) <= 3}
    nb = {t for t in tb if t.isdigit() and not _YEAR.match(t) and len(t) <= 3}
    if na and nb and na.isdisjoint(nb):
        score *= 0.4
    aa, ab = bool(ta & ACCESSORY_WORDS), bool(tb & ACCESSORY_WORDS)
    if aa != ab:
        score *= 0.25
    ya, yb = {int(t) for t in ta if _YEAR.match(t)}, {int(t) for t in tb if _YEAR.match(t)}
    if ya and yb:
        gap = min(abs(x - y) for x in ya for y in yb)
        score *= max(0.3, 1 - 0.12 * gap)
    return round(min(1.0, score), 4)


def weighted_percentile(values: Sequence[float], weights: Sequence[float], pct: float) -> float:
    """Ağırlıklı yüzdelik (orta nokta enterpolasyonu; eşit ağırlıkta klasik yüzdeliğe yakındır)."""
    pairs = sorted(zip(values, weights))
    vals = [v for v, _ in pairs]
    ws = [max(0.0, w) for _, w in pairs]
    total = sum(ws)
    if not vals:
        return 0.0
    if total <= 0:
        return _plain_percentile(vals, pct)
    centers, acc = [], 0.0
    for w in ws:
        centers.append(acc + w / 2)
        acc += w
    target = pct / 100 * total
    if target <= centers[0]:
        return vals[0]
    if target >= centers[-1]:
        return vals[-1]
    for i in range(1, len(vals)):
        if target <= centers[i]:
            span = centers[i] - centers[i - 1]
            frac = (target - centers[i - 1]) / span if span > 0 else 0.0
            return vals[i - 1] + frac * (vals[i] - vals[i - 1])
    return vals[-1]


def _plain_percentile(values: Sequence[float], pct: float) -> float:
    s = sorted(values)
    if not s:
        return 0.0
    k = (len(s) - 1) * pct / 100
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def select_comps(
    target_title: str,
    comps: Iterable[MarketListing],
    *,
    exclude_id: int | None = None,
    currency: str = "TL",
    min_similarity: float = 0.5,
) -> list[tuple[float, MarketListing]]:
    """Hedefe benzeyen, tekrarları ve aykırı fiyatları ayıklanmış emsaller: [(benzerlik, ilan)]."""
    pool = [c for c in comps if c.id != exclude_id and c.price and c.price > 0 and c.currency == currency]
    if not pool:
        return []
    scored = [(title_similarity(target_title, c.title), c) for c in pool]
    scored = [(s, c) for s, c in scored if s >= min_similarity]
    # aynı başlık+fiyat tekrarlarını (yeniden yayınlanan ilanlar) tekilleştir
    unique: dict[tuple[str, float], tuple[float, MarketListing]] = {}
    for s, c in scored:
        key = (" ".join(sorted(_token_set(c.title))), round(c.price or 0))
        if key not in unique or unique[key][0] < s:
            unique[key] = (s, c)
    scored = list(unique.values())
    prices = [c.price or 0.0 for _, c in scored]
    if len(prices) >= 4:
        q1, q3 = _plain_percentile(prices, 25), _plain_percentile(prices, 75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        med = _plain_percentile(prices, 50)
        scored = [(s, c) for s, c in scored if lo <= (c.price or 0) <= hi and 0.35 * med <= (c.price or 0) <= 3 * med]
    return scored


def summarize(scored: list[tuple[float, MarketListing]], resale_percentile: float = 45.0,
              max_refs: int = 12) -> MarketEstimate:
    if not scored:
        return MarketEstimate()
    values = [float(c.price or 0) for _, c in scored]
    weights = [s for s, _ in scored]
    median = weighted_percentile(values, weights, 50)
    p25 = weighted_percentile(values, weights, 25)
    p75 = weighted_percentile(values, weights, 75)
    resale = weighted_percentile(values, weights, resale_percentile)
    n = len(values)
    mean_sim = sum(weights) / n
    spread = (p75 - p25) / median if median else 1.0
    confidence = min(1.0, n / 10) * max(0.15, 1 - min(1.0, spread)) * mean_sim
    refs = sorted(scored, key=lambda sc: -sc[0])[:max_refs]
    return MarketEstimate(
        n=n,
        median=round(median),
        p25=round(p25),
        p75=round(p75),
        low=round(min(values)),
        high=round(max(values)),
        resale=round(resale),
        mean_similarity=round(mean_sim, 3),
        confidence=round(min(1.0, confidence * 1.25), 3),
        comps=[
            CompRef(listing_id=c.id, title=c.title, price=float(c.price or 0), similarity=round(s, 3), url=c.url)
            for s, c in refs
        ],
    )


def estimate_market(
    target_title: str,
    comps: Iterable[MarketListing],
    *,
    exclude_id: int | None = None,
    currency: str = "TL",
    resale_percentile: float = 45.0,
    min_similarity: float = 0.5,
    max_refs: int = 12,
) -> MarketEstimate:
    scored = select_comps(
        target_title, comps, exclude_id=exclude_id, currency=currency, min_similarity=min_similarity
    )
    return summarize(scored, resale_percentile=resale_percentile, max_refs=max_refs)


def histogram(values: Sequence[float], bins: int = 8) -> list[dict[str, float]]:
    if not values:
        return []
    lo, hi = min(values), max(values)
    if hi <= lo:
        return [{"from": lo, "to": hi, "count": len(values)}]
    step = (hi - lo) / bins
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int((v - lo) / step))
        counts[idx] += 1
    return [{"from": round(lo + i * step), "to": round(lo + (i + 1) * step), "count": c} for i, c in enumerate(counts)]


def price_suggestions(estimate: MarketEstimate) -> dict[str, float | None]:
    """Kendi ilanın için fiyat önerileri."""
    if not estimate.n or estimate.median is None:
        return {"quick": None, "fair": None, "high": None}
    quick = estimate.p25 if estimate.p25 is not None else estimate.median
    return {
        "quick": _round_price(quick * 0.98),
        "fair": _round_price(estimate.median),
        "high": _round_price(estimate.p75 or estimate.median),
    }


def _round_price(value: float) -> float:
    step = 50 if value < 2000 else 100 if value < 20000 else 250 if value < 100000 else 1000
    return float(round(value / step) * step)
