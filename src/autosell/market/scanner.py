"""Takip listelerini tarar, yeni/ucuzlayan ilanları fiyat araştırmasıyla puanlar,
kârlı al-sat fırsatlarını kaydeder ve bildirir.

Hız için tarama hattı:

1. Arama sonuçları: derin taramada birkaç sayfa; arada yalnızca en yeniye sıralı ilk
   sayfa (sayfanın tamamı yeni ilansa bir sonrakine geçilir). Tarama tarayıcısı resim
   indirmez ve kartlar görünür görünmez okunur.
2. Emsal ilanlarla piyasa değeri ve kural tabanlı puan.
3. Hızlı karar motoru (Jev / Laya): aksesuar, farklı model, kusurlu ve şüpheli ilanlar
   detay sayfası açılmadan saniyeler içinde elenir.
4. Kalan en iyi adayların detay sayfası (açıklamadaki riskler) ve açıklamayla yeniden karar.
5. Fırsat hemen bildirilir. Daha yavaş olan yapay zekâ (LLM) incelemesi tarayıcıyı
   bekletmeden ayrı bir işte yapılır; kararı değişirse düzeltme bildirimi gider.

Siteye giden her sayfa isteği platformun saatlik bütçesinden düşülür (bkz. safety.py).
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..ai.base import AIError, LLMProvider
from ..ai.decision import DecisionEngine
from ..automation.browser import BrowserSession
from ..automation.driver import PageDriver
from ..automation.guards import is_captcha
from ..automation.interaction import HumanTimeout, Interaction
from ..automation.platforms import get_adapter
from ..config import Settings
from ..db import Database
from ..models import Deal, MarketEstimate, MarketListing, ScrapedListing, Watch, now_iso
from ..safety import RequestBudget, ScanBlocked
from ..textutil import contains_phrase, format_price
from .deals import apply_ai_review, detect_risks, evaluate_deal
from .evaluator import ai_review
from .extract import extract_cards, extract_details
from .fastcheck import Entry, FastChecker
from .notify import deal_message, deal_update_message, send_telegram
from .pricing import estimate_market, histogram, price_suggestions, select_comps, summarize

log = logging.getLogger(__name__)
BLOCK_TEXTS = (
    "erisim engellendi", "access denied", "too many requests", "cok fazla istek", "gecici olarak engellendi",
    "olagan disi erisim", "olagandisi erisim", "istek sinirini", "request blocked",
)
# Bu puanın üstündeki ilanlar (ya da fırsat sayılanlar) aday kabul edilir
CANDIDATE_SCORE = 40.0


class BudgetExhausted(RuntimeError):
    """Saatlik güvenli istek sınırı doldu; tarama sonra yapılacak."""


@dataclass
class ScanSummary:
    watch_id: int | None = None
    deep: bool = False
    pages: int = 0
    total: int = 0
    new: int = 0
    price_changed: int = 0
    evaluated: int = 0
    fast_checked: int = 0
    fast_rejected: int = 0
    deals: int = 0
    ai_reviews: int = 0
    notified: int = 0
    seconds: float = 0.0
    message: str = ""
    # Yapay zekâ incelemesine gönderilecek fırsatlar (ayrı işte incelenir)
    review_ids: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def is_candidate(deal: Deal) -> bool:
    return deal.is_deal or deal.score >= CANDIDATE_SCORE


class MarketScanner:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        provider: LLMProvider | None,
        interaction: Interaction,
        shots_dir: Path,
        *,
        decision: DecisionEngine | None = None,
        budget: RequestBudget | None = None,
    ):
        self.db = db
        self.settings = settings
        self.provider = provider
        self.interaction = interaction
        self.shots_dir = shots_dir
        self.decision = decision
        self.budget = budget
        self.pages_read = 0
        self._budget_warned = False

    def log(self, message: str) -> None:
        self.interaction.log(message)

    # ------------------------------------------------------------- toplama

    def _spend(self, what: str) -> bool:
        """Saatlik bütçeden bir sayfa isteği düşer; bütçe bittiyse False."""
        if self.budget is None or self.budget.take():
            return True
        if not self._budget_warned:
            self._budget_warned = True
            self.log(f"⏳ Saatlik güvenli istek sınırına ulaşıldı ({self.budget.per_hour}/saat); {what} sonraki "
                     "taramaya bırakıldı.")
        return False

    def _guard(self, driver: PageDriver, status: int | None = None) -> None:
        """Site erişimi engellediyse (403/429, "erişim engellendi") ya da CAPTCHA çözülmezse
        ScanBlocked fırlatır; böylece o platformun taraması bir süre duraklatılır."""
        snap = driver.snapshot()
        text = snap.norm_text
        if status in (403, 429) or any(w in text for w in BLOCK_TEXTS):
            raise ScanBlocked(f"Site erişimi kısıtladı (HTTP {status or '-'}).")
        if is_captcha(snap):
            try:
                self.interaction.wait_for_human(
                    "Site güvenlik doğrulaması (CAPTCHA) istiyor. Lütfen tarayıcıda çözün; çözülmezse "
                    "tarama hesabınızı korumak için bir süre duraklatılacak.",
                    done=lambda: not is_captcha(driver.snapshot()),
                    page=driver.page,
                    timeout_s=min(180, self.settings.browser.human_timeout_s),
                )
            except HumanTimeout as exc:
                raise ScanBlocked("CAPTCHA çözülmedi.") from exc

    def collect(
        self,
        session: BrowserSession,
        platform: str,
        *,
        query: str = "",
        url: str = "",
        price_min: float | None = None,
        price_max: float | None = None,
        max_pages: int | None = None,
        quick_pages: int | None = None,
        watch_id: int | None = None,
    ) -> list[ScrapedListing]:
        """Arama sonuçlarını okur. quick_pages verilirse o kadar sayfadan sonra yalnızca sayfadaki
        ilanların hepsi yeniyse (bu takipte daha önce görülmediyse) sonraki sayfaya geçilir."""
        adapter = get_adapter(platform, self.settings, None, self.interaction, self.shots_dir)
        if not url and not query:
            raise ValueError("Arama için bir kelime ya da arama bağlantısı gerekli.")
        if not self._spend("arama"):
            wait = self.budget.minutes_until() if self.budget else 0
            raise BudgetExhausted(f"Saatlik güvenli istek sınırı doldu; yaklaşık {wait} dakika sonra tekrar "
                                  "denenecek (Ayarlar > Fırsat Avcısı).")
        driver = PageDriver(session.page(f"tarama-{platform}"), self.settings.browser, self.log)
        target = adapter.search_url(query=query, url=url, price_min=price_min, price_max=price_max)
        self.log(f"🔎 {adapter.display_name} araması açılıyor: {target}")
        card_selector = (adapter.ps.card_selectors or {}).get("card") or None
        self._guard(driver, driver.goto(target, wait_for=card_selector))
        items: dict[str, ScrapedListing] = {}
        pages = max(1, max_pages or self.settings.market.max_pages)
        self.pages_read = 0
        for page_no in range(pages):
            self.interaction.check_cancelled()
            found = extract_cards(driver.page, platform, adapter.ps)
            self.pages_read += 1
            before = len(items)
            for item in found:
                items.setdefault(item.external_id, item)
            self.log(f"Sayfa {page_no + 1}: {len(found)} ilan okundu ({len(items) - before} yeni).")
            if page_no + 1 >= pages or not found:
                break
            if quick_pages is not None and page_no + 1 >= quick_pages and watch_id is not None:
                known = self.db.known_external_ids(platform, [i.external_id for i in found], watch_id=watch_id)
                if known:
                    break  # en yeniye sıralı listede daha önce görülen ilana ulaşıldı
            if not self._spend("sonraki sayfalar"):
                break
            driver.pause(2.5)  # siteyi yormamak için
            if not adapter.next_page(driver, page_no + 1):
                break
            self._guard(driver)
        if not items:
            path = driver.screenshot(self.shots_dir / f"tarama-{platform}-{now_iso()[:19].replace(':', '')}.png")
            if path:
                self.interaction.attach_screenshot(path)
            self.log("⚠ Sayfada ilan okunamadı. Arama bağlantısını ya da Ayarlar > Platformlar > kart "
                     "seçicilerini kontrol edin.")
        return list(items.values())

    def fetch_details(self, session: BrowserSession, listing: MarketListing) -> dict[str, Any]:
        if not listing.url or not self._spend("detay sayfaları"):
            return {}
        driver = PageDriver(session.page(f"detay-{listing.platform}"), self.settings.browser, self.log)
        try:
            self._guard(driver, driver.goto(listing.url))
            details = extract_details(driver.page)
        except ScanBlocked:
            raise
        except Exception as exc:  # detay alınamazsa tarama sürsün
            self.log(f"Detay sayfası okunamadı ({listing.external_id}): {str(exc)[:100]}")
            return {}
        slim = {
            "description": details.get("description", ""),
            "attributes": details.get("attributes", {}),
            "fetched_at": now_iso(),
        }
        self.db.set_listing_details(listing.id, slim)
        driver.pause(2.0)
        return slim

    # ------------------------------------------------------------- takip taraması

    @staticmethod
    def accept(item: ScrapedListing, watch: Watch) -> bool:
        if item.price is None or item.currency != "TL":
            return False
        if watch.price_min is not None and item.price < watch.price_min:
            return False
        if watch.price_max is not None and item.price > watch.price_max:
            return False
        if watch.include_words and not any(contains_phrase(item.title, w) for w in watch.include_words):
            return False
        if any(contains_phrase(item.title, w) for w in watch.exclude_words):
            return False
        return True

    def _estimate(self, listing: MarketListing, comps: list[MarketListing]) -> MarketEstimate:
        return estimate_market(
            listing.title,
            comps,
            exclude_id=listing.id,
            currency=listing.currency,
            resale_percentile=self.settings.market.resale_percentile,
        )

    def deep_scan_due(self, watch: Watch, now: datetime | None = None) -> bool:
        last = _parse(watch.last_deep_scan_at)
        if watch.last_run_at is None or last is None:
            return True
        hours = max(0.0, self.settings.market.deep_scan_hours)
        return (now or datetime.now(timezone.utc)) - last >= timedelta(hours=hours)

    def _fast_checker(self) -> FastChecker | None:
        if self.decision is None:
            return None
        d = self.settings.decision

        def cached(listing_id: int) -> dict[str, Any] | None:
            deal = self.db.get_deal_by_listing(listing_id)
            return deal.fast if deal else None

        return FastChecker(self.decision, threshold=d.threshold, log=self.log, cached=cached)

    def _notify(self, deal: Deal, listing: MarketListing) -> bool:
        token, chat = self.settings.telegram_token(), self.settings.telegram_chat_id()
        if (not token or not chat or not deal.is_deal or deal.notified or deal.status == "gizli"
                or deal.score < self.settings.notify.min_score):
            return False
        ok, detail = send_telegram(token, chat, deal_message(deal, listing))
        if not ok:
            self.log(f"Bildirim gönderilemedi: {detail}")
            return False
        deal.notified = True
        self.db.save_deal(deal)
        return True

    def scan_watch(self, session: BrowserSession, watch: Watch) -> ScanSummary:
        started = time.monotonic()
        market = self.settings.market
        summary = ScanSummary(watch_id=watch.id, deep=self.deep_scan_due(watch))
        if summary.deep:
            items = self.collect(session, watch.platform, query=watch.query, url=watch.search_url,
                                 price_min=watch.price_min, price_max=watch.price_max, max_pages=market.max_pages)
        else:
            items = self.collect(session, watch.platform, query=watch.query, url=watch.search_url,
                                 price_min=watch.price_min, price_max=watch.price_max,
                                 max_pages=max(market.max_pages, market.quick_pages),
                                 quick_pages=max(1, market.quick_pages), watch_id=watch.id)
        summary.pages = self.pages_read
        accepted = [i for i in items if self.accept(i, watch)]
        summary.total = len(accepted)
        now = now_iso()
        first_run = watch.last_run_at is None
        to_evaluate: list[MarketListing] = []
        for item in accepted:
            listing, change = self.db.upsert_listing(item, watch.id, now)
            if change == "new":
                summary.new += 1
            elif change == "price_changed":
                summary.price_changed += 1
            if change != "seen" or first_run:
                to_evaluate.append(listing)

        since = (datetime.now(timezone.utc) - timedelta(days=market.comp_days)).replace(microsecond=0).isoformat()
        comps = self.db.listings_for_watch(watch.id or 0, since=since)
        entries: list[Entry] = []
        for listing in to_evaluate:
            est = self._estimate(listing, comps)
            entries.append((listing, est, evaluate_deal(listing, est, market, watch)))
        summary.evaluated = len(entries)

        # 1) Hızlı karar: aksesuar / farklı model / kusurlu / şüpheli adaylar detay açılmadan elenir
        query = watch.query.strip() or watch.name
        checker = self._fast_checker()
        if checker:
            limit = max(0, self.settings.decision.max_checks)
            candidates = sorted((e for e in entries if is_candidate(e[2])), key=lambda e: -e[2].score)[:limit]
            summary.fast_rejected += checker.check(candidates, query)

        # 2) Elenmeyen en iyi adayların detay sayfası (açıklamadaki riskler) ve açıklamayla yeniden karar
        refreshed = self._fetch_top_details(session, entries, watch)
        if checker and refreshed:
            summary.fast_rejected += checker.check(refreshed, query)
        summary.fast_checked = checker.asked if checker else 0

        # 3) Kaydet ve hemen bildir
        for listing, _est, deal in sorted(entries, key=lambda e: -e[2].score):
            if deal.comps_count == 0:
                continue
            saved = self.db.save_deal(deal)
            if not saved.is_deal:
                continue
            summary.deals += 1
            self.log(f"🔥 Fırsat: {listing.title[:60]} — {format_price(listing.price)} → "
                     f"tahmini kâr {format_price(saved.est_profit)} (puan {saved.score:.0f})")
            if self._notify(saved, listing):
                summary.notified += 1
            if saved.id is not None and not saved.ai and len(summary.review_ids) < max(0, market.ai_evaluations):
                summary.review_ids.append(saved.id)

        summary.seconds = round(time.monotonic() - started, 1)
        summary.message = (
            f"{summary.total} ilan, {summary.new} yeni, {summary.price_changed} fiyat değişikliği, "
            f"{summary.deals} fırsat"
        )
        if summary.fast_rejected:
            summary.message += f", {summary.fast_rejected} elendi"
        watch.last_run_at = now_iso()
        if summary.deep:
            watch.last_deep_scan_at = watch.last_run_at
        watch.last_status = summary.message
        watch.last_found = summary.deals
        self.db.save_watch(watch)
        kind = "derin" if summary.deep else "hızlı"
        self.log(f"✔ Tarama bitti ({kind}, {summary.pages} sayfa, {summary.seconds:.1f} sn): {summary.message}")
        return summary

    def _fetch_top_details(self, session: BrowserSession, entries: list[Entry], watch: Watch) -> list[Entry]:
        market = self.settings.market
        budget = max(0, market.fetch_details)
        refreshed: list[Entry] = []
        for i in sorted(range(len(entries)), key=lambda k: -entries[k][2].score):
            if budget <= 0:
                break
            listing, est, deal = entries[i]
            if listing.details or not is_candidate(deal):
                continue
            budget -= 1
            details = self.fetch_details(session, listing)
            if details:
                listing.details = details
                entries[i] = (listing, est, evaluate_deal(listing, est, market, watch))
                refreshed.append(entries[i])
        return refreshed

    # ------------------------------------------------------------- yapay zekâ incelemesi

    def review_deals(self, deal_ids: list[int]) -> dict[str, Any]:
        """Fırsatları yapay zekâyla inceler. Tarayıcı gerektirmez; tarama bunu beklemez.
        Bildirilmiş bir fırsat artık fırsat sayılmıyorsa düzeltme bildirimi gönderilir."""
        if self.provider is None:
            return {"reviewed": 0}
        market = self.settings.market
        since = (datetime.now(timezone.utc) - timedelta(days=market.comp_days)).replace(microsecond=0).isoformat()
        token, chat = self.settings.telegram_token(), self.settings.telegram_chat_id()
        reviewed = flipped = notified = 0
        for deal_id in deal_ids:
            self.interaction.check_cancelled()
            deal = self.db.get_deal(deal_id)
            listing = self.db.get_listing(deal.listing_id) if deal else None
            if not deal or not listing or not deal.is_deal or deal.ai:
                continue
            comps = self.db.listings_for_watch(deal.watch_id, since=since) if deal.watch_id else \
                self.db.listings_for_platform(listing.platform, since=since)
            est = self._estimate(listing, comps)
            was_notified = deal.notified
            try:
                self.log(f"🤖 Yapay zekâ değerlendiriyor: {listing.title[:60]}")
                review = ai_review(self.provider, listing, est, deal, market, web_research=self.settings.ai.web_research)
            except AIError as exc:
                self.log(f"Yapay zekâ değerlendirmesi atlandı: {exc}")
                continue
            apply_ai_review(deal, review, market)
            reviewed += 1
            saved = self.db.save_deal(deal)
            if not saved.is_deal:
                flipped += 1
                self.log(f"🤖 Yapay zekâ bu ilanı fırsat saymadı: {listing.title[:60]}")
                if was_notified and token and chat:
                    send_telegram(token, chat, deal_update_message(saved, listing))
            elif self._notify(saved, listing):
                notified += 1
        return {"reviewed": reviewed, "flipped": flipped, "notified": notified}

    # ------------------------------------------------------------- piyasa araştırması

    def research(
        self,
        session: BrowserSession,
        platform: str,
        *,
        query: str = "",
        url: str = "",
        max_pages: int | None = None,
    ) -> dict[str, Any]:
        items = self.collect(session, platform, query=query, url=url, max_pages=max_pages)
        now = now_iso()
        listings = [self.db.upsert_listing(i, None, now)[0] for i in items if i.price and i.currency == "TL"]
        if query:
            scored = select_comps(query, listings, min_similarity=0.45)
        else:
            scored = select_comps(" ".join(_common_words(listings)), listings, min_similarity=0.3)
        est = summarize(scored, resale_percentile=self.settings.market.resale_percentile, max_refs=40)
        prices = [float(c.price or 0) for _, c in scored]
        result = {
            "platform": platform,
            "query": query,
            "url": url,
            "scanned": len(items),
            "matched": est.n,
            "estimate": est.model_dump(),
            "suggestions": price_suggestions(est),
            "histogram": histogram(prices),
            "risky": [
                {"title": c.title, "price": c.price, "url": c.url, "risks": [f.text for f in detect_risks(c, est)]}
                for _, c in scored if detect_risks(c, est)
            ][:10],
        }
        if est.n:
            self.log(f"📊 {est.n} benzer ilan: medyan {format_price(est.median)}, "
                     f"aralık {format_price(est.p25)} – {format_price(est.p75)}")
        else:
            self.log("Yeterli benzer ilan bulunamadı.")
        return result


def _common_words(listings: list[MarketListing], k: int = 4) -> list[str]:
    from collections import Counter

    from ..textutil import tokens

    counts = Counter(t for listing in listings for t in set(tokens(listing.title)))
    return [w for w, _ in counts.most_common(k)]
