"""Başlık puanlama: yapay zekânın ürettiği adaylar arasından en iyisini seçer.

Puan; uzunluk kullanımı, marka/modelin başta olması, anahtar kelime kapsamı ve
güven sinyallerini ödüllendirir; iletişim bilgisi, emoji, aşırı noktalama,
büyük harf ve kelime tekrarını (keyword stuffing) cezalandırır.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..models import ProductInfo, TitleCandidate
from ..textutil import contains_phrase, has_contact_info, normalize, strip_emoji, unique_preserve
from .rules import PlatformRules

TRUST_WORDS = (
    "garantili", "faturalı", "kutulu", "hatasız", "sorunsuz", "az kullanılmış", "sıfır ayarında",
    "bakımlı", "değişensiz", "boyasız", "tramersiz", "ilk sahibinden", "servis bakımlı", "pil %",
    "orijinal", "temiz", "yeni gibi", "etiketli",
)
HYPE_WORDS = ("acil", "kaçmaz", "kaçırmayın", "süper", "fırsat", "bedava", "en ucuz", "şok", "müthiş", "efsane")


def _covers(title_norm_tokens: set[str], title: str, keyword: str) -> bool:
    if contains_phrase(title, keyword):
        return True
    kw_tokens = normalize(keyword).split()
    return bool(kw_tokens) and all(t in title_norm_tokens for t in kw_tokens)


def score_title(
    title: str,
    *,
    rules: PlatformRules,
    keywords: Iterable[str] = (),
    brand: str = "",
    model: str = "",
) -> TitleCandidate:
    notes: list[str] = []
    score = 40.0
    n = len(title)
    if n > rules.title_max:
        score -= 40
        notes.append(f"Karakter sınırı aşılıyor ({n}/{rules.title_max})")
    elif n < rules.title_min:
        score -= 20
        notes.append(f"Çok kısa ({n} karakter)")
    else:
        util = n / rules.title_max
        if util >= 0.7:
            score += 10
            notes.append(f"Uzunluk ideal ({n}/{rules.title_max})")
        elif util >= 0.5:
            score += 5
            notes.append(f"Uzunluk yeterli ({n}/{rules.title_max})")
        else:
            notes.append(f"Kısa kalmış ({n}/{rules.title_max}); anahtar kelime eklenebilir")

    norm = normalize(title)
    norm_tokens = set(norm.split())
    if brand and _covers(norm_tokens, title, brand):
        score += 8
    if model:
        if _covers(norm_tokens, title, model):
            score += 10
            pos = norm.find(normalize(model))
            if 0 <= pos <= 22:
                score += 5
                notes.append("Model adı başta (aramada öne çıkar)")
        else:
            notes.append("Model adı geçmiyor")

    kws = [k for k in unique_preserve(keywords) if normalize(k)][:8]
    if kws:
        weights = [1 / (1 + 0.35 * i) for i in range(len(kws))]
        covered = sum(w for k, w in zip(kws, weights) if _covers(norm_tokens, title, k))
        coverage = covered / sum(weights)
        score += 20 * coverage
        notes.append(f"Anahtar kelime kapsamı %{round(coverage * 100)}")

    trust = [w for w in TRUST_WORDS if normalize(w) and normalize(w) in norm]
    if trust:
        score += min(8, 4 * len(trust))
        notes.append("Güven sinyali: " + ", ".join(trust[:3]))

    if has_contact_info(title):
        score -= 50
        notes.append("İletişim bilgisi içeriyor (kurallara aykırı)")
    if not rules.use_emoji and strip_emoji(title) != title:
        score -= 10
        notes.append("Emoji içeriyor")
    if re.search(r"[!?*]{2,}|\.{4,}|-{3,}", title):
        score -= 8
        notes.append("Aşırı noktalama")
    letters = [c for c in title if c.isalpha()]
    if letters and rules.title_style != "upper":
        upper_ratio = sum(c.isupper() for c in letters) / len(letters)
        if upper_ratio > 0.6:
            score -= 8
            notes.append("Fazla büyük harf")
    words = [t for t in norm.split() if len(t) > 2 and not t.isdigit()]
    duplicates = len(words) - len(set(words))
    if duplicates:
        score -= 6 * duplicates
        notes.append("Tekrarlanan kelime (anahtar kelime doldurma)")
    hype = [w for w in HYPE_WORDS if contains_phrase(title, w)]
    if hype:
        score -= 3 * len(hype)
        notes.append("Arama değeri düşük abartı kelimesi: " + ", ".join(hype))

    return TitleCandidate(text=title, score=round(max(0.0, min(100.0, score)), 1), notes=notes)


def rank_titles(
    candidates: Iterable[str],
    product: ProductInfo,
    rules: PlatformRules,
    truncated: Iterable[str] = (),
) -> list[TitleCandidate]:
    keywords = [product.brand, product.model, *product.keywords]
    cut = set(truncated)
    scored = []
    for i, text in enumerate(unique_preserve(candidates)):
        cand = score_title(text, rules=rules, keywords=keywords, brand=product.brand, model=product.model)
        if text in cut:
            cand.score = max(0.0, cand.score - 5)
            cand.notes.append("Sınıra sığması için kısaltıldı")
        scored.append((i, cand))
    scored.sort(key=lambda pair: (-pair[1].score, pair[0]))
    return [c for _, c in scored]
