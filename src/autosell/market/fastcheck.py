"""Fırsat adaylarını hızlı karar motoruyla (Jev / Laya) saniyeler içinde süzme.

Kural tabanlı puanlama başlık benzerliğine dayanır; "iPhone 13 kutusu", "13 mini" ya da
"PS5 kolu" gibi ilanlar ucuz göründüğü için sahte fırsat üretebilir. Karar motoru her aday
için dört soruyu tek istekte cevaplar:

- ilan_turu: ürünün kendisi mi, yalnızca aksesuar/parça mı, alım/takas ilanı mı?
- ayni_urun: fiyatı belirleyen emsal ilanlarla aynı model/kapasite mi?
- kusurlu:   arızalı, hasarlı, kilitli, ağır hasar kayıtlı ya da parça olarak mı?
- supheli:   kapora/ön ödeme, kayıt dışı (IMEI) ya da replika şüphesi var mı?
"""

from __future__ import annotations

import hashlib
import json
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from ..ai.decision import DecisionEngine, DecisionError, choice, noul
from ..models import Deal, MarketEstimate, MarketListing, RiskFlag
from ..textutil import format_price

LISTING_QUESTIONS: dict[str, Any] = {
    "ilan_turu": {
        "type": "choice",
        "instructions": "Bu ilanda satılan şey nedir?",
        "criteria": {
            "urun": "ürünün kendisi satılıyor (yanında hediye aksesuar olabilir)",
            "aksesuar_parca": "yalnızca kutu, kılıf, şarj aleti, kablo, jant, ekran ya da yedek parça",
            "alim_takas": "satış değil: alım ilanı (alınır, aranıyor) ya da yalnızca takas",
            "diger": "başka bir şey",
        },
    },
    "ayni_urun": {
        "type": "noul",
        "instructions": "İlandaki ürün, emsal ilanlardaki ürünle aynı model ve aynı kapasitede/sürümde mi?",
    },
    "kusurlu": {
        "type": "noul",
        "instructions": "İlana göre ürün arızalı, hasarlı, kırık, kilitli (iCloud/hesap kilidi), ağır hasar "
                        "kayıtlı ya da parça olarak mı satılıyor?",
    },
    "supheli": {
        "type": "noul",
        "instructions": "İlan kapora veya ön ödeme istiyor mu, ya da ürün kayıt dışı (yurt dışı, IMEI kaydı yok) "
                        "veya replika mı?",
    },
}

_TYPE_REJECT = {
    "aksesuar_parca": "Yalnızca aksesuar / yedek parça ilanı",
    "alim_takas": "Satış ilanı değil (alım ya da takas)",
    "diger": "Aranan ürün satılmıyor",
}

Entry = tuple[MarketListing, MarketEstimate, Deal]


def listing_state(listing: MarketListing, estimate: MarketEstimate, query: str = "") -> dict[str, Any]:
    details = listing.details or {}
    ilan: dict[str, Any] = {"baslik": listing.title, "fiyat": format_price(listing.price, listing.currency)}
    if details.get("description"):
        ilan["aciklama"] = str(details["description"])[:1500]
    if details.get("attributes"):
        ilan["ozellikler"] = dict(list(details["attributes"].items())[:20])
    state: dict[str, Any] = {"ilan": ilan, "emsal_ilanlar": [c.title for c in estimate.comps[:3]]}
    if query.strip():
        state["aranan"] = query.strip()
    return state


def state_key(state: dict[str, Any]) -> str:
    raw = json.dumps(state, ensure_ascii=False, sort_keys=True) + json.dumps(LISTING_QUESTIONS, sort_keys=True)
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def apply_decision(deal: Deal, answers: dict[str, Any], threshold: float = 0.6, engine: str = "") -> Deal:
    """Karar motoru cevaplarını fırsata işler: eleme kararları ilanı fırsat olmaktan çıkarır."""
    kind, kind_p = choice(answers, "ilan_turu")
    same = noul(answers, "ayni_urun")
    faulty = noul(answers, "kusurlu")
    shady = noul(answers, "supheli")
    rejects: list[str] = []
    if kind in _TYPE_REJECT and kind_p >= threshold:
        rejects.append(_TYPE_REJECT[kind])
    if same is not None and same <= 1 - threshold:
        rejects.append("Emsallerden farklı model / kapasite; fiyat karşılaştırması geçersiz")
    if faulty is not None and faulty >= threshold:
        rejects.append("Arızalı, hasarlı ya da kilitli görünüyor")
    if shady is not None and shady >= threshold:
        rejects.append("Kapora, kayıt dışı ya da replika şüphesi")
    for text in rejects:
        flag = f"⚡ {text}"
        if not any(f.text == flag for f in deal.risk_flags):
            deal.risk_flags.append(RiskFlag(level="yuksek", text=flag))
    if rejects:
        deal.is_deal = False
        deal.score = round(min(deal.score, 30.0), 1)
    elif kind == "urun" and (same is None or same >= threshold):
        ok = "⚡ Hızlı kontrol: aynı ürün, kusur ya da şüphe işareti yok"
        if ok not in deal.reasons:
            deal.reasons.append(ok)
    deal.fast = {
        "motor": engine,
        "ilan_turu": kind,
        "ilan_turu_olasilik": round(kind_p, 2),
        "ayni_urun": None if same is None else round(same, 2),
        "kusurlu": None if faulty is None else round(faulty, 2),
        "supheli": None if shady is None else round(shady, 2),
        "elendi": bool(rejects),
    }
    return deal


class FastChecker:
    """Adayları paralel olarak karar motoruna sorar; aynı ilan tekrar sorulmaz."""

    def __init__(
        self,
        engine: DecisionEngine,
        *,
        threshold: float = 0.6,
        workers: int = 4,
        log: Callable[[str], None] | None = None,
        cached: Callable[[int], dict[str, Any] | None] | None = None,
    ):
        self.engine = engine
        self.threshold = threshold
        self.workers = max(1, workers)
        self.say = log or (lambda _m: None)
        self.cached = cached or (lambda _id: None)
        self.failed = False
        self.asked = 0
        self._memo: dict[int, tuple[str, dict[str, Any]]] = {}

    def _answers_for(self, listing_id: int, key: str) -> dict[str, Any] | None:
        memo = self._memo.get(listing_id)
        if memo and memo[0] == key:
            return memo[1]
        stored = self.cached(listing_id) or {}
        if stored.get("anahtar") == key and isinstance(stored.get("cevaplar"), dict):
            return stored["cevaplar"]
        return None

    def check(self, entries: list[Entry], query: str = "") -> int:
        """Girdilerdeki fırsatlara kararları işler (yerinde); elenen ilan sayısını döner."""
        if self.failed or not entries:
            return 0
        jobs: list[tuple[Entry, dict[str, Any], str]] = []
        for entry in entries:
            state = listing_state(entry[0], entry[1], query)
            jobs.append((entry, state, state_key(state)))
        todo = [(entry, state, key) for entry, state, key in jobs if self._answers_for(entry[0].id, key) is None]
        started = time.monotonic()
        if todo:
            with ThreadPoolExecutor(max_workers=min(self.workers, len(todo))) as pool:
                results = list(pool.map(lambda job: self._ask(job[1]), todo))
            for (entry, _state, key), answers in zip(todo, results):
                if answers is not None:
                    self._memo[entry[0].id] = (key, answers)
            self.asked += sum(1 for r in results if r is not None)
        rejected = 0
        for (listing, _est, deal), _state, key in jobs:
            answers = self._answers_for(listing.id, key)
            if answers is None:
                continue
            apply_decision(deal, answers, self.threshold, self.engine.name)
            deal.fast = {**(deal.fast or {}), "anahtar": key, "cevaplar": answers}
            rejected += int(deal.fast.get("elendi", False))
        if todo and not self.failed:
            self.say(f"⚡ Hızlı karar ({self.engine.name}): {len(jobs)} aday {time.monotonic() - started:.1f} sn'de "
                     f"incelendi, {rejected} ilan elendi.")
        return rejected

    def _ask(self, state: dict[str, Any]) -> dict[str, Any] | None:
        if self.failed:
            return None
        try:
            return self.engine.decide(state, LISTING_QUESTIONS)
        except DecisionError as exc:
            if not self.failed:
                self.failed = True
                self.say(f"⚠ Hızlı karar motoru kullanılamadı, kural tabanlı puanlamayla devam ediliyor: {exc}")
            return None
