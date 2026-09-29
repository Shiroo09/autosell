"""Uygulama servisi: web paneli ve komut satırının kullandığı üst düzey işlemler."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Iterable

from .ai import AINotConfigured, LLMProvider, build_provider
from .ai.decision import DecisionEngine, DecisionError
from .ai.schemas import STR, obj
from .automation.browser import BrowserPool, BrowserSession
from .automation.interaction import Cancelled
from .automation.platforms import PublishCancelled, get_adapter
from .config import PLATFORM_NAMES, PLATFORMS, Settings, SettingsStore, resolve_paths
from .db import Database
from .images import save_upload
from .jobs import Job, JobInteraction, JobManager
from .listing import ListingGenerator, basic_listing
from .market.fastcheck import LISTING_QUESTIONS, listing_text, questions_for
from .market.notify import send_telegram
from .market.scanner import BudgetExhausted, MarketScanner
from .models import Draft, PlatformListing, PublicationStatus, Watch, now_iso
from .safety import (
    PublishBlocked,
    ScanBlocked,
    check_publish,
    cooldown,
    request_budget,
    scan_browser,
    set_cooldown,
)
from .scheduler import WatchScheduler

log = logging.getLogger(__name__)

EDITABLE_DRAFT_FIELDS = {"notes", "price", "currency", "platforms", "photos", "listings"}


class AutoSell:
    def __init__(self, data_dir: str | Path | None = None, *, start_scheduler: bool = False):
        self.paths = resolve_paths(data_dir)
        self.settings_store = SettingsStore(self.paths.settings_file)
        self.db = Database(self.paths.db_file)
        self.pool = BrowserPool(self.paths.browser_dir, self.settings_store.get)
        self.jobs = JobManager(self.pool)
        self.provider_override: LLMProvider | None = None
        self.decision_override: DecisionEngine | None = None
        self.scheduler = WatchScheduler(self)
        if start_scheduler:
            self.scheduler.start()

    @property
    def settings(self) -> Settings:
        return self.settings_store.get()

    def provider(self, required: bool = True) -> LLMProvider | None:
        if self.provider_override is not None:
            return self.provider_override
        try:
            return build_provider(self.settings)
        except AINotConfigured:
            if required:
                raise
            return None

    def decision_ready(self) -> bool:
        """Karar motoru açık ve kullanılabilir ayarlarda mı (Jev için API anahtarı gerekir)."""
        settings = self.settings
        endpoint = settings.decision_endpoint()
        return endpoint is not None and (settings.decision.engine != "jev" or bool(endpoint[1]))

    def decision_engine(self) -> DecisionEngine | None:
        """Hızlı karar motoru (Jev / Laya); kapalıysa ya da Jev için anahtar yoksa None."""
        if self.decision_override is not None:
            return self.decision_override
        if not self.decision_ready():
            return None
        settings = self.settings
        base, key, model = settings.decision_endpoint()  # type: ignore[misc]
        try:
            return DecisionEngine(base, key, model, name=settings.decision.engine,
                                  timeout=max(3.0, settings.decision.timeout_s))
        except DecisionError:
            return None

    def budget_status(self) -> dict[str, dict[str, int]]:
        out = {}
        for platform in PLATFORMS:
            budget = request_budget(self.db, self.settings, platform)
            out[platform] = {"used": budget.used(), "limit": budget.per_hour, "free_in_min": budget.minutes_until()}
        return out

    def shutdown(self) -> None:
        self.scheduler.stop()
        self.jobs.shutdown()
        self.pool.shutdown()
        self.db.close()

    # ----------------------------------------------------------------- taslaklar

    def draft_or_404(self, draft_id: str) -> Draft:
        draft = self.db.get_draft(draft_id)
        if not draft:
            raise KeyError(f"Taslak bulunamadı: {draft_id}")
        return draft

    def photo_paths(self, draft: Draft) -> list[Path]:
        base = self.paths.draft_dir(draft.id)
        return [base / name for name in draft.photos if (base / name).exists()]

    def _store_photos(self, draft: Draft, photos: Iterable[tuple[str, bytes]]) -> None:
        base = self.paths.draft_dir(draft.id)
        base.mkdir(parents=True, exist_ok=True)
        start = len(draft.photos)
        for i, (_name, data) in enumerate(photos, start=start + 1):
            if not data:
                continue
            target = base / f"foto-{i:02d}"
            while target.with_suffix(".jpg").exists():
                i += 1
                target = base / f"foto-{i:02d}"
            saved = save_upload(data, target)
            draft.photos.append(saved.name)

    def create_draft(
        self,
        notes: str = "",
        price: float | None = None,
        platforms: list[str] | None = None,
        photos: Iterable[tuple[str, bytes]] = (),
    ) -> Draft:
        chosen = [p for p in (platforms or []) if p in PLATFORMS] or [
            p for p in PLATFORMS if self.settings.platform(p).enabled
        ] or list(PLATFORMS)
        draft = Draft(notes=notes.strip(), price=price, platforms=chosen)
        self._store_photos(draft, photos)
        return self.db.save_draft(draft)

    def add_photos(self, draft_id: str, photos: Iterable[tuple[str, bytes]]) -> Draft:
        draft = self.draft_or_404(draft_id)
        self._store_photos(draft, photos)
        return self.db.save_draft(draft)

    def delete_photo(self, draft_id: str, name: str) -> Draft:
        draft = self.draft_or_404(draft_id)
        if name in draft.photos:
            draft.photos.remove(name)
            path = self.paths.draft_dir(draft_id) / Path(name).name
            path.unlink(missing_ok=True)
        return self.db.save_draft(draft)

    def update_draft(self, draft_id: str, patch: dict[str, Any]) -> Draft:
        draft = self.draft_or_404(draft_id)
        data = draft.model_dump()
        for key, value in patch.items():
            if key not in EDITABLE_DRAFT_FIELDS:
                continue
            if key == "photos":
                value = [p for p in value if p in draft.photos] + [p for p in draft.photos if p not in value]
            if key == "platforms":
                value = [p for p in value if p in PLATFORMS]
            if key == "listings":
                merged = dict(data["listings"])
                for platform, listing in (value or {}).items():
                    if platform in PLATFORMS:
                        merged[platform] = PlatformListing.model_validate(
                            {**merged.get(platform, {}), **listing}
                        ).model_dump()
                value = merged
            data[key] = value
        updated = Draft.model_validate(data)
        return self.db.save_draft(updated)

    def delete_draft(self, draft_id: str) -> None:
        self.db.delete_draft(draft_id)
        shutil.rmtree(self.paths.draft_dir(draft_id), ignore_errors=True)

    def _set_publication(self, draft_id: str, platform: str, status: str, **fields: Any) -> None:
        draft = self.db.get_draft(draft_id)
        if not draft:
            return
        current = draft.publications.get(platform, PublicationStatus())
        data = current.model_dump()
        data.update(fields)
        data["status"] = status
        data["updated_at"] = now_iso()
        draft.publications[platform] = PublicationStatus.model_validate(data)
        self.db.save_draft(draft)

    # ---------------------------------------------------------------- işler

    def start_generate(self, draft_id: str) -> Job:
        self.draft_or_404(draft_id)

        def run(job: Job, ui: JobInteraction, _session: BrowserSession | None) -> dict[str, Any]:
            draft = self.draft_or_404(draft_id)
            try:
                provider = self.provider()
            except AINotConfigured as exc:
                basic_listing(draft, self.settings)
                draft.last_error = str(exc)
                self.db.save_draft(draft)
                ui.log("Yapay zekâ ayarlı değil; notlardan basit bir taslak hazırlandı. "
                       "Ayarlar > Yapay Zekâ bölümünden bir sağlayıcı tanımlayın.", "warning")
                raise
            ListingGenerator(provider, self.settings).generate(draft, self.photo_paths(draft), ui.log)
            self.db.save_draft(draft)
            ui.log("✔ İlan metinleri hazır.")
            return {"draft_id": draft.id}

        return self.jobs.submit("generate", "İlan metinleri oluşturuluyor", run, draft_id=draft_id)

    def start_publish(self, draft_id: str, platform: str, force: bool = False) -> Job:
        if platform not in PLATFORMS:
            raise ValueError(f"Bilinmeyen platform: {platform}")
        draft = self.draft_or_404(draft_id)
        existing = self.jobs.find_active("publish", draft_id=draft_id, platform=platform)
        if existing:
            return existing
        if self.jobs.find_active("publish", platform=platform):
            raise PublishBlocked("Bu platformda şu an başka bir ilan veriliyor; bitmesini bekleyin.", "busy")
        check_publish(self.db, self.settings, draft, platform, force=force)

        def run(job: Job, ui: JobInteraction, session: BrowserSession | None) -> dict[str, Any]:
            assert session is not None
            current = self.draft_or_404(draft_id)
            self._set_publication(draft_id, platform, "calisiyor", job_id=job.id, message="")
            adapter = get_adapter(platform, self.settings, self.provider(required=False), ui, self.paths.shots_dir)
            if adapter.provider is None:
                ui.log("Not: yapay zekâ tanımlı değil; yalnız sezgisel eşleştirme kullanılacak.", "warning")
            try:
                result = adapter.publish(session, current, self.photo_paths(current))
            except (PublishCancelled, Cancelled) as exc:
                self._set_publication(draft_id, platform, "iptal", message=str(exc))
                raise Cancelled(str(exc)) from exc
            except Exception as exc:
                self._set_publication(draft_id, platform, "hata", message=str(exc)[:300])
                raise
            self._set_publication(
                draft_id, platform, "yayinda", url=result.url, listing_no=result.listing_no, message=result.message
            )
            listing = current.listings.get(platform)
            self.db.log_publish(platform, draft_id, listing.title if listing else current.display_title(),
                                result.url, result.listing_no)
            return {"status": result.status, "url": result.url, "listing_no": result.listing_no,
                    "message": result.message, "report": result.report}

        name = PLATFORM_NAMES[platform]
        return self.jobs.submit("publish", f"{name}: {draft.display_title()[:50]}", run, browser=platform,
                                platform=platform, draft_id=draft_id)

    def start_login(self, platform: str) -> Job:
        if platform not in PLATFORMS:
            raise ValueError(f"Bilinmeyen platform: {platform}")
        existing = self.jobs.find_active("login", platform=platform)
        if existing:
            return existing

        def run(job: Job, ui: JobInteraction, session: BrowserSession | None) -> dict[str, Any]:
            assert session is not None
            adapter = get_adapter(platform, self.settings, None, ui, self.paths.shots_dir)
            adapter.login(session)
            return {"logged_in": True}

        return self.jobs.submit("login", f"{PLATFORM_NAMES[platform]} girişi", run, browser=platform,
                                platform=platform)

    def scan_cooldown(self, platform: str) -> dict[str, str] | None:
        return cooldown(self.db, platform)

    def _mark_blocked(self, platform: str, reason: str) -> str:
        minutes = self.settings.market.block_cooldown_min
        until = set_cooldown(self.db, platform, minutes, reason)
        return (f"{PLATFORM_NAMES.get(platform, platform)} erişimi kısıtladı ({reason}). Hesabınızı korumak için "
                f"tarama {minutes} dakika duraklatıldı (≈ {until.astimezone().strftime('%H:%M')}).")

    def start_scan(self, watch_id: int, scheduled: bool = False) -> Job:
        watch = self.db.get_watch(watch_id)
        if not watch:
            raise KeyError(f"Takip listesi bulunamadı: {watch_id}")
        existing = self.jobs.find_active("scan", watch_id=watch_id)
        if existing:
            return existing
        self._check_scan_allowed(watch.platform)

        def run(job: Job, ui: JobInteraction, session: BrowserSession | None) -> dict[str, Any]:
            assert session is not None
            current = self.db.get_watch(watch_id)
            if not current:
                raise KeyError("Takip listesi silinmiş.")
            engine = self.decision_engine()
            scanner = MarketScanner(self.db, self.settings, None, ui, self.paths.shots_dir, decision=engine,
                                    budget=request_budget(self.db, self.settings, current.platform))
            try:
                summary = scanner.scan_watch(session, current)
            except ScanBlocked as exc:
                message = self._mark_blocked(current.platform, str(exc))
                self._scan_failed(watch_id, message)
                raise RuntimeError(message) from exc
            except BudgetExhausted:
                raise  # zaman işlenmez: bütçe açılınca zamanlayıcı yeniden dener
            except Exception as exc:
                self._scan_failed(watch_id, f"Hata: {str(exc)[:160]}")  # zamanlayıcı siteyi sıkıştırmasın
                raise
            finally:
                if engine is not None and engine is not self.decision_override:
                    engine.close()
            if summary.review_ids:
                self.start_review(summary.review_ids, current.platform)
            return summary.to_dict()

        title = f"{'⏱ ' if scheduled else ''}Tarama: {watch.name}"
        return self.jobs.submit("scan", title, run, browser=scan_browser(watch.platform), platform=watch.platform,
                                watch_id=watch_id)

    def _check_scan_allowed(self, platform: str) -> None:
        name = PLATFORM_NAMES[platform]
        paused = self.scan_cooldown(platform)
        if paused:
            raise ValueError(f"{name} taraması {paused['until_local']} saatine kadar duraklatıldı: {paused['reason']}")
        budget = request_budget(self.db, self.settings, platform)
        if budget.left() < 1:
            raise ValueError(f"{name} için saatlik güvenli istek sınırı doldu ({budget.per_hour}/saat). Hesabınızı "
                             f"ve IP adresinizi korumak için yaklaşık {budget.minutes_until()} dakika sonra tekrar "
                             "deneyin (sınır: Ayarlar > Fırsat Avcısı).")

    def _scan_failed(self, watch_id: int, message: str) -> None:
        failed = self.db.get_watch(watch_id)
        if failed:
            failed.last_run_at = now_iso()
            failed.last_status = message[:200]
            self.db.save_watch(failed)

    def start_review(self, deal_ids: list[int], platform: str | None = None) -> Job | None:
        """Fırsatların yapay zekâ incelemesi: tarayıcı gerektirmez, taramayı bekletmez."""
        provider = self.provider(required=False)
        if provider is None or not deal_ids:
            return None

        def run(job: Job, ui: JobInteraction, _session: BrowserSession | None) -> dict[str, Any]:
            scanner = MarketScanner(self.db, self.settings, provider, ui, self.paths.shots_dir)
            return scanner.review_deals(deal_ids)

        return self.jobs.submit("review", f"Yapay zekâ incelemesi ({len(deal_ids)} fırsat)", run, platform=platform)

    def start_research(self, platform: str, query: str = "", url: str = "", draft_id: str | None = None) -> Job:
        if platform not in PLATFORMS:
            raise ValueError(f"Bilinmeyen platform: {platform}")
        if not query.strip() and not url.strip():
            raise ValueError("Arama kelimesi ya da bağlantı girin.")
        self._check_scan_allowed(platform)

        def run(job: Job, ui: JobInteraction, session: BrowserSession | None) -> dict[str, Any]:
            assert session is not None
            scanner = MarketScanner(self.db, self.settings, None, ui, self.paths.shots_dir,
                                    budget=request_budget(self.db, self.settings, platform))
            try:
                return scanner.research(session, platform, query=query.strip(), url=url.strip())
            except ScanBlocked as exc:
                raise RuntimeError(self._mark_blocked(platform, str(exc))) from exc

        return self.jobs.submit("research", f"Fiyat araştırması: {query or url}"[:80], run,
                                browser=scan_browser(platform), platform=platform, draft_id=draft_id)

    def research_query_for(self, draft: Draft) -> str:
        product = draft.product
        if product.brand or product.model:
            base = " ".join(x for x in (product.brand, product.model) if x)
            key_attrs = [a.value for p in draft.listings.values() for a in p.attributes
                         if any(k in a.name.lower() for k in ("hafıza", "hafiza", "depolama", "kapasite"))]
            return " ".join([base, *key_attrs[:1]]).strip()
        for listing in draft.listings.values():
            if listing.title:
                return listing.title
        return draft.notes.splitlines()[0] if draft.notes.strip() else ""

    # ---------------------------------------------------------------- testler

    def test_ai(self) -> dict[str, Any]:
        provider = self.provider()
        assert provider is not None
        schema = obj({"cevap": STR})
        data = provider.generate_json(
            system="Kısa ve net yanıt ver.",
            prompt="Bağlantı testi: 'cevap' alanına yalnızca 'tamam' yaz.",
            schema=schema,
            max_tokens=2000,
        )
        return {"ok": True, "provider": provider.describe(), "answer": data.get("cevap", "")}

    def test_decision(self) -> dict[str, Any]:
        """Karar motorunu 4 örnek ilanla sınar (temiz ilan, kutu ilanı, farklı model, kapora).
        Türkçe ilanlarda güvenilir olmayan bir motor (ör. eğitilmemiş Laya) böylece hemen görülür."""
        import time

        from .ai.decision import choice, noul

        engine = self.decision_engine()
        if engine is None:
            d = self.settings.decision
            if d.engine == "kapali":
                raise DecisionError("Hızlı karar motoru kapalı. Bir sağlayıcı seçip adresini girin.")
            if not d.base_url.strip():
                raise DecisionError("Karar motoru için sunucu adresi girilmedi (ör. https://openrouter.ai/api/v1 "
                                    "ya da kendi Laya sunucunuz).")
            raise DecisionError("Jev için API anahtarı yok. Bu bölüme sağlayıcınızın (ör. OpenRouter, TypeSafe) "
                                "anahtarını girin.")
        comps = ["Apple iPhone 13 128 GB Mavi", "iPhone 13 128GB Gece Yarısı Kutulu", "iPhone 13 128 GB Yıldız Işığı"]
        cases = [  # (başlık, fiyat, açıklama, beklenen: tür, aynı ürün, kusurlu, şüpheli)
            ("iPhone 13 128 GB Mavi Temiz", "27.500 TL", "Tek elden, sorunsuz, kutulu faturalı.", ("urun", True, False, False)),
            ("iPhone 13 128 GB kutusu ve şarj aleti", "1.500 TL", "Sadece kutu ve orijinal şarj aleti, telefon yoktur.",
             ("aksesuar_parca", None, None, None)),
            ("iPhone 13 mini 128 GB", "21.000 TL", "Temiz, kutulu.", ("urun", False, False, False)),
            ("iPhone 13 128 GB sıfır ayarında", "15.000 TL", "Kapora gönderin kargoya vereyim, önce ödeme.",
             ("urun", True, False, True)),
        ]
        correct = total = 0
        first_kind = None
        started = time.monotonic()
        try:
            for title, price, desc, expected in cases:
                state = listing_text(title, price, desc, "iPhone 13 128 GB", comps=comps)
                answers = {}
                for name, question in questions_for(state).items():
                    answers.update(engine.decide(state, {name: question}))
                kind, _ = choice(answers, "ilan_turu")
                first_kind = first_kind or kind
                got = (kind, (noul(answers, "ayni_urun") or 0) >= 0.5, (noul(answers, "kusurlu") or 0) >= 0.5,
                       (noul(answers, "supheli") or 0) >= 0.5)
                for exp, val in zip(expected, got):
                    if exp is not None:
                        total += 1
                        correct += int(exp == val)
        finally:
            if engine is not self.decision_override:
                engine.close()
        ms = round((time.monotonic() - started) * 1000 / len(cases))
        reliable = correct >= total - 1
        return {"ok": True, "engine": engine.describe(), "ms": ms, "answer": first_kind, "correct": correct,
                "total": total, "reliable": reliable,
                "verdict": ("Türkçe ilanlarda güvenilir görünüyor." if reliable else
                            "Bu motor Türkçe ilanlarda güvenilir değil; iyi fırsatları da eleyebilir. "
                            "Jev'i kullanın ya da motoru kapatın.")}

    def test_telegram(self) -> tuple[bool, str]:
        s = self.settings
        return send_telegram(s.telegram_token(), s.telegram_chat_id(), "✅ AutoSell bildirim testi başarılı.")

    # ---------------------------------------------------------------- takip

    def save_watch(self, data: dict[str, Any], watch_id: int | None = None) -> Watch:
        base = self.db.get_watch(watch_id).model_dump() if watch_id else {}
        if watch_id and not base:
            raise KeyError(f"Takip listesi bulunamadı: {watch_id}")
        merged = {**base, **{k: v for k, v in data.items() if k not in ("id", "last_run_at", "last_status",
                                                                        "last_found", "created_at",
                                                                        "last_deep_scan_at")}}
        watch = Watch.model_validate(merged)
        watch.id = watch_id
        watch.interval_min = max(watch.interval_min, self.settings.market.min_interval_min)
        if not watch.query.strip() and not watch.search_url.strip():
            raise ValueError("Takip için arama kelimesi ya da arama bağlantısı girin.")
        return self.db.save_watch(watch)
