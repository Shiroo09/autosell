"""Takip listelerini tarar, yeni/ucuzlayan ilanları fiyat araştırmasıyla puanlar,
kârlı al-sat fırsatlarını kaydeder ve bildirir."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ..ai.base import AIError, LLMProvider
from ..automation.browser import BrowserSession
from ..automation.driver import PageDriver
from ..automation.guards import is_captcha
from ..automation.interaction import Interaction
from ..automation.platforms import get_adapter
from ..config import Settings
from ..db import Database
from ..models import Deal, MarketEstimate, MarketListing, ScrapedListing, Watch, now_iso
from ..textutil import contains_phrase, format_price
from .deals import apply_ai_review, detect_risks, evaluate_deal
from .evaluator import ai_review
from .extract import extract_cards, extract_details
from .notify import deal_message, send_telegram
from .pricing import estimate_market, histogram, price_suggestions, select_comps, summarize

log = logging.getLogger(__name__)


@dataclass
class ScanSummary:
    watch_id: int | None = None
    total: int = 0
    new: int = 0
    price_changed: int = 0
    evaluated: int = 0
    deals: int = 0
    ai_reviews: int = 0
    notified: int = 0
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MarketScanner:
    def __init__(
        self,
        db: Database,
        settings: Settings,
        provider: LLMProvider | None,
        interaction: Interaction,
        shots_dir: Path,
    ):
        self.db = db
        self.settings = settings
        self.provider = provider
        self.interaction = interaction
        self.shots_dir = shots_dir

    def log(self, message: str) -> None:
        self.interaction.log(message)

    # ------------------------------------------------------------- toplama

    def _guard(self, driver: PageDriver) -> None:
        if is_captcha(driver.snapshot()):
            self.interaction.wait_for_human(
                "Site güvenlik doğrulaması (CAPTCHA) istiyor. Lütfen tarayıcı penceresinde çözün.",
                done=lambda: not is_captcha(driver.snapshot()),
                page=driver.page,
                timeout_s=min(300, self.settings.browser.human_timeout_s),
            )

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
    ) -> list[ScrapedListing]:
        adapter = get_adapter(platform, self.settings, None, self.interaction, self.shots_dir)
        if not url and not query:
            raise ValueError("Arama için bir kelime ya da arama bağlantısı gerekli.")
        driver = PageDriver(session.page(f"tarama-{platform}"), self.settings.browser, self.log)
        target = adapter.search_url(query=query, url=url, price_min=price_min, price_max=price_max)
        self.log(f"🔎 {adapter.display_name} araması açılıyor: {target}")
        driver.goto(target)
        self._guard(driver)
        items: dict[str, ScrapedListing] = {}
        pages = max(1, max_pages or self.settings.market.max_pages)
        for page_no in range(pages):
            self.interaction.check_cancelled()
            found = extract_cards(driver.page, platform, adapter.ps)
            before = len(items)
            for item in found:
                items.setdefault(item.external_id, item)
            self.log(f"Sayfa {page_no + 1}: {len(found)} ilan okundu ({len(items) - before} yeni).")
            if page_no + 1 >= pages or not found:
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
        if not listing.url:
            return {}
        driver = PageDriver(session.page(f"detay-{listing.platform}"), self.settings.browser, self.log)
        try:
            driver.goto(listing.url)
            self._guard(driver)
            details = extract_details(driver.page)
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

    def scan_watch(self, session: BrowserSession, watch: Watch) -> ScanSummary:
        market = self.settings.market
        summary = ScanSummary(watch_id=watch.id)
        items = self.collect(
            session, watch.platform, query=watch.query, url=watch.search_url,
            price_min=watch.price_min, price_max=watch.price_max,
        )
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
        evaluated: list[tuple[MarketListing, MarketEstimate, Deal]] = []
        for listing in to_evaluate:
            est = self._estimate(listing, comps)
            evaluated.append((listing, est, evaluate_deal(listing, est, market, watch)))
        summary.evaluated = len(evaluated)

        # En iyi adayların detay sayfasını açıp açıklamadaki risklere bak
        ranked = sorted(evaluated, key=lambda e: -e[2].score)
        detail_budget = max(0, market.fetch_details)
        for i, (listing, est, deal) in enumerate(ranked):
            if detail_budget <= 0:
                break
            if not (deal.is_deal or deal.score >= 40) or listing.details:
                continue
            detail_budget -= 1
            details = self.fetch_details(session, listing)
            if details:
                listing.details = details
                ranked[i] = (listing, est, evaluate_deal(listing, est, market, watch))

        # Yapay zekâ değerlendirmesi (en iyi birkaç fırsat için)
        ai_budget = max(0, market.ai_evaluations) if self.provider else 0
        for i, (listing, est, deal) in enumerate(sorted(ranked, key=lambda e: -e[2].score)):
            if ai_budget <= 0:
                break
            if not deal.is_deal:
                continue
            ai_budget -= 1
            try:
                self.log(f"🤖 Yapay zekâ değerlendiriyor: {listing.title[:60]}")
                review = ai_review(self.provider, listing, est, deal, market,  # type: ignore[arg-type]
                                   web_research=self.settings.ai.web_research)
                apply_ai_review(deal, review, market)
                summary.ai_reviews += 1
            except AIError as exc:
                self.log(f"Yapay zekâ değerlendirmesi atlandı: {exc}")

        min_notify = self.settings.notify.min_score
        token, chat = self.settings.telegram_token(), self.settings.telegram_chat_id()
        for listing, est, deal in ranked:
            if deal.comps_count == 0:
                continue
            saved = self.db.save_deal(deal)
            if saved.is_deal:
                summary.deals += 1
                self.log(f"🔥 Fırsat: {listing.title[:60]} — {format_price(listing.price)} → "
                         f"tahmini kâr {format_price(saved.est_profit)} (puan {saved.score:.0f})")
                if token and chat and not saved.notified and saved.score >= min_notify and saved.status != "gizli":
                    ok, detail = send_telegram(token, chat, deal_message(saved, listing))
                    if ok:
                        saved.notified = True
                        self.db.save_deal(saved)
                        summary.notified += 1
                    else:
                        self.log(f"Bildirim gönderilemedi: {detail}")

        summary.message = (
            f"{summary.total} ilan, {summary.new} yeni, {summary.price_changed} fiyat değişikliği, "
            f"{summary.deals} fırsat"
        )
        watch.last_run_at = now_iso()
        watch.last_status = summary.message
        watch.last_found = summary.deals
        self.db.save_watch(watch)
        self.log(f"✔ Tarama bitti: {summary.message}")
        return summary

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
