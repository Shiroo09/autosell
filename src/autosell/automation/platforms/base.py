"""Platform adaptörlerinin ortak ilan verme akışı.

Akış bir durum makinesidir: her adımda sayfanın anlık görüntüsü alınır ve sayfa
sınıflandırılır (giriş, CAPTCHA, doğrulama kodu, kategori seçimi, ilan formu,
doping/öne çıkarma, önizleme/onay, başarı). Sezgisel yöntemler ilerleyemezse
yapay zekâ adım ajanı, o da olmazsa kullanıcı devreye girer. Ödeme adımları asla
otomatik geçilmez.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...ai.base import LLMProvider
from ...config import PLATFORM_NAMES, Settings
from ...models import Draft, PlatformListing, now_iso
from ...textutil import best_match, normalize, similarity
from ..agent import AgentResult, StepAgent
from ..browser import BrowserSession
from ..chooser import Chooser
from ..driver import Clickable, PageDriver, Snapshot
from ..form_filler import FillContext, FillReport, FormFiller, classify
from ..guards import (
    extract_listing_no,
    has_password_field,
    is_captcha,
    is_payment_clickable,
    is_payment_page,
    is_payment_text,
    is_success,
    needs_verification_code,
)
from ..interaction import Interaction

log = logging.getLogger(__name__)


class PublishError(RuntimeError):
    pass


class PaymentBlocked(PublishError):
    pass


class PublishCancelled(PublishError):
    pass


@dataclass
class PublishResult:
    status: str
    url: str = ""
    listing_no: str = ""
    message: str = ""
    screenshot: str = ""
    report: dict[str, Any] = field(default_factory=dict)


@dataclass
class FlowState:
    category_done: bool = False
    form_done: bool = False
    publish_clicked: bool = False
    fix_attempts: int = 0
    agent_runs: int = 0
    human_waits: int = 0
    reopened: bool = False


NOISE_EXACT = {"geri", "iptal", "vazgec", "kapat", "degistir", "tamam", "evet", "hayir", "kabul et", "reddet"}
NOISE_PHRASES = ("yardim", "nasil", "hakkinda", "kurallar", "destek", "sss", "cikis", "giris yap", "uye ol",
                 "hesap ac", "cerez", "gizlilik", "iletisim", "tumunu gor", "daha fazla")


class PlatformAdapter:
    name = "base"
    post_button_texts: list[str] = ["Ücretsiz İlan Ver", "İlan Ver"]
    continue_texts = [
        "Devam", "Devam Et", "İleri", "Sonraki", "Sonraki Adım", "Kaydet ve Devam Et", "Kaydet ve Devam",
        "Önizle", "İlanı Önizle", "Önizlemeye Geç",
    ]
    publish_texts = [
        "İlanı Yayınla", "Yayınla", "İlanı Onayla", "Onayla ve Yayınla", "Yayına Al", "İlanı Gönder",
        "Şimdi Yayınla", "İlanımı Yayınla", "Tamamla ve Yayınla", "İlanı Tamamla",
    ]
    promo_skip_texts = [
        "Doping istemiyorum", "Doping istemiyorum, devam et", "Dopingsiz devam et", "Doping almadan devam et",
        "Şimdi değil", "Hayır, teşekkürler", "Atla", "Bu adımı atla", "Ücretsiz devam et",
        "Öne çıkarmadan devam et", "Devam et (ücretsiz)",
    ]
    promo_words = ("doping", "one cikar", "vitrin", "daha fazla goruntulenme", "ust siradayim", "fark edilsin")
    logged_out_texts = ["Giriş Yap", "Üye Ol", "Hesap Aç", "Giriş yap / Üye ol"]
    logged_in_texts = ["Çıkış", "Çıkış Yap", "Bana Özel", "Hesabım", "Profilim", "İlanlarım", "Mesajlarım"]
    view_listing_texts = ["İlanı Görüntüle", "İlanımı Gör", "İlana Git", "İlanı gör", "İlanlarıma Git"]
    max_steps = 45

    def __init__(
        self,
        settings: Settings,
        provider: LLMProvider | None,
        interaction: Interaction,
        shots_dir: Path,
    ):
        self.settings = settings
        self.ps = settings.platform(self.name)
        self.provider = provider
        self.interaction = interaction
        self.shots_dir = shots_dir
        self.chooser = Chooser(provider, self.log)

    @property
    def display_name(self) -> str:
        return PLATFORM_NAMES.get(self.name, self.name)

    def log(self, message: str) -> None:
        self.interaction.log(message)

    def screenshot(self, driver: PageDriver, tag: str) -> str:
        path = self.shots_dir / f"{self.name}-{now_iso()[:19].replace(':', '')}-{tag}.png"
        saved = driver.screenshot(path)
        if saved:
            self.interaction.attach_screenshot(saved)
        return str(saved or "")

    # ------------------------------------------------------------------ giriş

    def login_state(self, snap: Snapshot) -> bool | None:
        texts = [c.text for c in snap.clickables]
        if any(similarity(t, x) >= 0.9 for t in texts for x in self.logged_in_texts):
            return True
        if any(similarity(t, x) >= 0.9 for t in texts for x in self.logged_out_texts):
            return False
        return None

    def looks_like_login(self, snap: Snapshot) -> bool:
        url = snap.url.lower()
        if any(k in url for k in ("/giris", "/login", "signin", "/oturum")):
            return True
        return has_password_field(snap)

    def is_logged_in(self, driver: PageDriver) -> bool:
        snap = driver.snapshot()
        if self.looks_like_login(snap):
            return False
        return self.login_state(snap) is True

    def login(self, session: BrowserSession) -> bool:
        driver = PageDriver(session.page("main"), self.settings.browser, self.log)
        driver.goto(self.ps.login_url or self.ps.home_url)
        snap = driver.snapshot()
        if not self.looks_like_login(snap) and self.login_state(snap) is True:
            self.log(f"{self.display_name}: oturum zaten açık.")
            return True
        if not self.looks_like_login(snap):
            btn = snap.find_clickable(self.logged_out_texts, threshold=0.85, include_chrome=True)
            if btn:
                driver.click(btn.id)
                driver.settle()
        self.interaction.wait_for_human(
            f"Açılan tarayıcı penceresinde {self.display_name} hesabınıza giriş yapın "
            "(SMS/doğrulama adımları dahil). Giriş algılanınca otomatik devam edilecek.",
            done=lambda: self.is_logged_in(driver),
            page=driver.page,
            timeout_s=self.settings.browser.human_timeout_s,
        )
        self.log(f"✔ {self.display_name} oturumu açıldı ve kaydedildi.")
        return True

    # ------------------------------------------------------------ ilan verme

    def fill_context(self, draft: Draft, listing: PlatformListing, photos: list[Path]) -> FillContext:
        summary_lines = [
            f"Başlık: {listing.title}",
            f"Kategori (öneri): {' > '.join(listing.category_path)}",
            f"Ürün: {draft.product.name} | Marka: {draft.product.brand} | Model: {draft.product.model}",
            f"Durum: {draft.product.condition}",
            "Özellikler: " + "; ".join(f"{a.name}: {a.value}" for a in listing.attributes),
            f"Öne çıkanlar: {', '.join(draft.product.highlights)}",
            f"Kusurlar: {', '.join(draft.product.defects)}",
            f"Fiyat: {draft.price_for(self.name)} {draft.currency}",
            f"Satıcı notları: {draft.notes[:600]}",
        ]
        return FillContext(
            title=listing.title,
            description=listing.description,
            price=draft.price_for(self.name),
            currency=draft.currency,
            attributes=list(listing.attributes),
            photos=photos,
            seller=self.settings.seller,
            condition=draft.product.condition,
            highlights=list(draft.product.highlights),
            summary="\n".join(summary_lines),
        )

    def open_post_page(self, driver: PageDriver) -> None:
        if self.ps.post_url:
            driver.goto(self.ps.post_url)
            return
        driver.goto(self.ps.home_url)
        snap = driver.snapshot()
        btn = snap.find_clickable(
            self.post_button_texts, threshold=0.8, include_chrome=True, exclude=is_payment_clickable
        )
        if not btn:
            raise PublishError(
                f"{self.display_name} ana sayfasında ilan verme düğmesi bulunamadı. "
                "Ayarlar > Platformlar bölümüne ilan verme sayfasının adresini (post_url) girin."
            )
        self.log(f"'{btn.text}' düğmesine tıklanıyor...")
        before = list(driver.page.context.pages)
        driver.click(btn.id)
        driver.settle()
        new_pages = [p for p in driver.page.context.pages if p not in before]
        if new_pages:  # yeni sekmede açıldıysa oraya geç
            driver.page = new_pages[-1]
            driver.settle()

    def publish(self, session: BrowserSession, draft: Draft, photos: list[Path]) -> PublishResult:
        listing = draft.listings.get(self.name)
        if not listing or not listing.title:
            raise PublishError(f"Taslakta {self.display_name} için başlık/açıklama yok. Önce ilanı oluşturun.")
        if draft.price_for(self.name) is None:
            raise PublishError("İlan fiyatı girilmemiş.")
        driver = PageDriver(session.page(f"ilan-{draft.id}"), self.settings.browser, self.log)
        ctx = self.fill_context(draft, listing, photos)
        self.log(f"{self.display_name} ilan verme sayfası açılıyor...")
        self.open_post_page(driver)
        return self.run_flow(driver, ctx, listing)

    # ---------------------------------------------------------- sınıflandırma

    def is_category_candidate(self, c: Clickable) -> bool:
        if c.in_chrome or c.disabled or c.fixed:
            return False
        text = c.text.strip()
        if not 2 <= len(text) <= 60 or "\n" in text:
            return False
        n = normalize(text)
        if not n or n in NOISE_EXACT or any(p in n for p in NOISE_PHRASES):
            return False
        if is_payment_text(text):
            return False
        if any(similarity(text, t) >= 0.85 for t in self.continue_texts + self.publish_texts + self.promo_skip_texts):
            return False
        return True

    def has_listing_form(self, snap: Snapshot) -> bool:
        roles = [classify(f) for f in snap.fields if not f.in_chrome and not f.disabled]
        return any(r in ("title", "description", "price") for r in roles)

    def form_done_here(self, snap: Snapshot, ctx: FillContext) -> bool:
        for f in snap.fields:
            if f.in_chrome:
                continue
            role = classify(f)
            if role == "title" and f.value:
                return normalize(f.value) == normalize(ctx.title[: f.maxlength or len(ctx.title)])
            if role == "description" and f.value.strip():
                return True
        return False

    def looks_like_category(self, snap: Snapshot, path: list[str]) -> bool:
        if self.has_listing_form(snap):
            return False
        cands = [c for c in snap.clickables if self.is_category_candidate(c)]
        if not cands:
            return False
        texts = [c.text for c in cands]
        for element in path[:2]:
            if best_match(element, texts)[1] >= 0.8:
                return True
        return "kategori" in snap.norm_text and len(cands) >= 4 or "ne satiyorsun" in snap.norm_text

    def is_promo(self, snap: Snapshot) -> Clickable | None:
        text = snap.norm_text
        if not any(w in text for w in self.promo_words):
            return None
        return snap.find_clickable(self.promo_skip_texts, threshold=0.75, exclude=is_payment_clickable)

    def is_publish_text(self, text: str) -> bool:
        return any(similarity(text, t) >= 0.88 for t in self.publish_texts)

    def find_publish(self, snap: Snapshot) -> Clickable | None:
        return snap.find_clickable(self.publish_texts, threshold=0.88, exclude=is_payment_clickable)

    def find_continue(self, snap: Snapshot) -> Clickable | None:
        return snap.find_clickable(
            self.continue_texts,
            threshold=0.85,
            exclude=lambda c: is_payment_clickable(c) or self.is_publish_text(c.text),
        )

    # ---------------------------------------------------------- kategori seçimi

    def wait_for_new_options(self, driver: PageDriver, prev_ids: set[str], timeout_ms: int = 3500) -> Snapshot:
        waited = 0
        snap = driver.snapshot()
        while waited < timeout_ms:
            if self.has_listing_form(snap):
                return snap
            fresh = [c for c in snap.clickables if self.is_category_candidate(c) and c.id not in prev_ids]
            if fresh:
                return snap
            driver.page.wait_for_timeout(300)
            waited += 300
            snap = driver.snapshot()
        return snap

    def pick_category(
        self, pool: list[Clickable], path: list[str], path_idx: int, chosen: list[str], ctx: FillContext
    ) -> tuple[Clickable | None, int]:
        texts = [c.text for c in pool]
        for j in range(path_idx, min(len(path), path_idx + 3)):
            idx, score = best_match(path[j], texts)
            if idx >= 0 and score >= 0.8:
                return pool[idx], j + 1
        hint = path[path_idx] if path_idx < len(path) else None
        choice = self.chooser.pick_option(
            texts,
            hint=hint,
            context=ctx.summary,
            purpose=(
                f"{self.display_name} kategori ağacında bir sonraki seviyeyi seç. "
                f"Şu ana kadar seçilen: {' > '.join(chosen) or '(yok)'}. "
                f"Önerilen tam yol: {' > '.join(path) or '(yok)'}"
            ),
            threshold=0.8,
        )
        if choice:
            return pool[texts.index(choice)], path_idx + 1
        return None, path_idx

    def select_category(self, driver: PageDriver, path: list[str], ctx: FillContext) -> bool:
        chosen: list[str] = []
        path_idx = 0
        prev_ids: set[str] = set()
        snap = driver.snapshot()
        for level in range(12):
            if self.has_listing_form(snap):
                break
            cands = [c for c in snap.clickables if self.is_category_candidate(c)]
            fresh = [c for c in cands if c.id not in prev_ids]
            if level > 0 and not fresh:
                break  # yeni alt kategori çıkmadı: yaprak kategoriye ulaşıldı
            pool = fresh if level > 0 else cands
            pool = [c for c in pool if not any(similarity(c.text, x) >= 0.95 for x in chosen)] or pool
            pick, path_idx = self.pick_category(pool, path, path_idx, chosen, ctx)
            if pick is None:
                if level == 0:
                    return False
                break
            self.log(f"📂 Kategori: {pick.text}")
            prev_ids = {c.id for c in snap.clickables}
            driver.click(pick.id)
            chosen.append(pick.text)
            snap = self.wait_for_new_options(driver, prev_ids)
        if chosen:
            self.log("Seçilen kategori: " + " > ".join(chosen))
        return bool(chosen)

    # ------------------------------------------------------------ ana akış

    def check_confirmations(self, driver: PageDriver, snap: Snapshot) -> None:
        for f in snap.fields:
            if f.kind == "checkbox" and not f.checked and not f.in_chrome and classify(f) == "terms":
                driver.set_checked(f, True)
                self.log(f"☑ '{(f.option_text or f.label)[:70]}' işaretlendi.")

    def ask_human(self, driver: PageDriver, reason: str, state: FlowState) -> None:
        state.human_waits += 1
        if state.human_waits > 4:
            raise PublishError(f"İşlem tamamlanamadı: {reason}")
        self.screenshot(driver, "yardim")
        start_sig = driver.snapshot().signature()
        self.interaction.wait_for_human(
            f"{reason} Lütfen tarayıcıda gerekli adımı tamamlayın; sayfa değişince otomasyon devam edecek.",
            done=lambda: driver.snapshot().signature() != start_sig,
            page=driver.page,
            timeout_s=self.settings.browser.human_timeout_s,
        )

    def run_agent(self, driver: PageDriver, ctx: FillContext, goal: str, state: FlowState) -> bool:
        if not (self.provider and self.settings.browser.use_ai_agent) or state.agent_runs >= 3:
            return False
        state.agent_runs += 1
        self.log("🤖 Sezgisel adımlar yetmedi; yapay zekâ ajanı sayfayı inceliyor...")
        start_url = driver.page.url
        agent = StepAgent(self.provider, driver, self.interaction, self.settings.browser.agent_max_steps)
        outcome = agent.run(
            goal,
            ctx.summary,
            done=lambda s: s.url != start_url or is_success(s) or self.is_promo(s) is not None,
            forbidden_click=self.is_publish_text,
        )
        if outcome == AgentResult.PAYMENT:
            raise PaymentBlocked(agent.last_reason or "Ücretli bir adım algılandı.")
        if outcome == AgentResult.DONE:
            return True
        self.log(f"Yapay zekâ ajanı durdu: {agent.last_reason}")
        return False

    def final_publish(self, driver: PageDriver, state: FlowState) -> None:
        shot = self.screenshot(driver, "yayin-oncesi")
        if not self.ps.auto_publish:
            self.log("✅ İlan formu hazır. Tarayıcıda son kontrolü yapabilirsiniz.")
            answer = self.interaction.confirm(
                f"{self.display_name} ilanı yayınlansın mı?",
                page=driver.page,
                timeout_s=self.settings.browser.human_timeout_s,
                done=lambda: is_success(driver.snapshot()),
            )
            if answer is None:
                state.publish_clicked = True
                return
            if not answer:
                raise PublishCancelled("Yayınlama kullanıcı tarafından iptal edildi.")
        snap = driver.snapshot()
        if is_success(snap):
            state.publish_clicked = True
            return
        self.check_confirmations(driver, snap)
        btn = self.find_publish(snap)
        if not btn:
            raise PublishError("Yayınla düğmesi artık bulunamıyor (sayfa değişmiş olabilir).")
        self.log(f"🚀 '{btn.text}' tıklanıyor... {('(ekran görüntüsü: ' + shot + ')') if shot else ''}")
        driver.click(btn.id)
        state.publish_clicked = True
        driver.settle()

    def success_result(self, driver: PageDriver, snap: Snapshot, report: FillReport) -> PublishResult:
        listing_no = extract_listing_no(snap.text)
        view = snap.find_clickable(self.view_listing_texts, threshold=0.8)
        url = view.href if view and view.href else snap.url
        shot = self.screenshot(driver, "yayinlandi")
        message = "İlan oluşturuldu."
        if "kontrol edildikten sonra" in snap.norm_text or "onaya" in snap.norm_text:
            message = "İlan oluşturuldu; site kontrolünden sonra yayına alınacak."
        self.log(f"🎉 {self.display_name}: {message}" + (f" İlan No: {listing_no}" if listing_no else ""))
        return PublishResult(
            status="yayinda",
            url=url,
            listing_no=listing_no,
            message=message,
            screenshot=shot,
            report={
                "filled": report.filled,
                "ai_filled": report.ai_filled,
                "skipped": report.skipped,
                "photos": report.photos_uploaded,
            },
        )

    def run_flow(self, driver: PageDriver, ctx: FillContext, listing: PlatformListing) -> PublishResult:
        state = FlowState()
        report = FillReport()
        filler = FormFiller(driver, self.chooser, self.log)
        timeout = self.settings.browser.human_timeout_s
        last_sig = ""
        same = 0
        for _step in range(self.max_steps):
            self.interaction.check_cancelled()
            snap = driver.snapshot()

            if is_payment_page(snap):
                self.screenshot(driver, "odeme")
                raise PaymentBlocked(
                    "Ödeme sayfası açıldı; otomasyon durduruldu. Hiçbir ücretli işlem yapılmadı."
                )
            if is_success(snap) and (state.publish_clicked or state.form_done):
                return self.success_result(driver, snap, report)
            if is_captcha(snap):
                self.interaction.wait_for_human(
                    "Güvenlik doğrulaması (CAPTCHA) çıktı. Lütfen tarayıcıda çözün.",
                    done=lambda: not is_captcha(driver.snapshot()), page=driver.page, timeout_s=timeout,
                )
                continue
            if self.looks_like_login(snap):
                self.interaction.wait_for_human(
                    f"{self.display_name} hesabınıza giriş yapmanız gerekiyor. Lütfen tarayıcıda giriş yapın.",
                    done=lambda: not self.looks_like_login(driver.snapshot()), page=driver.page, timeout_s=timeout,
                )
                driver.settle()
                after = driver.snapshot()
                if not state.reopened and not (
                    self.has_listing_form(after) or self.looks_like_category(after, listing.category_path)
                ):
                    state.reopened = True
                    self.open_post_page(driver)
                continue
            if needs_verification_code(snap):
                self.interaction.wait_for_human(
                    "Telefonunuza gelen doğrulama kodunu tarayıcıda girin.",
                    done=lambda: not needs_verification_code(driver.snapshot()), page=driver.page, timeout_s=timeout,
                )
                continue
            driver.dismiss_cookie_banner()

            sig = snap.signature()
            same = same + 1 if sig == last_sig else 0
            last_sig = sig
            if same >= 2:
                if not self.run_agent(driver, ctx, "İlan verme akışında bir sonraki adıma geç "
                                      "(son yayınla düğmesine basma).", state):
                    self.ask_human(driver, "Otomasyon bu sayfada ilerleyemedi.", state)
                same = 0
                continue

            skip = self.is_promo(snap)
            if skip:
                self.log(f"💸 Ücretli öne çıkarma adımı atlanıyor: '{skip.text}'")
                driver.click(skip.id)
                driver.settle()
                continue

            if self.has_listing_form(snap) and not self.form_done_here(snap, ctx):
                self.log("📝 İlan formu dolduruluyor...")
                report.merge(filler.fill(ctx))
                state.form_done = True
                state.category_done = True
                if report.missing_required:
                    self.log("⚠ Doldurulamayan zorunlu alanlar: " + ", ".join(report.missing_required))
                continue

            if not state.category_done and self.looks_like_category(snap, listing.category_path):
                self.log("📂 Kategori seçiliyor: " + (" > ".join(listing.category_path) or "(öneri yok)"))
                if self.select_category(driver, listing.category_path, ctx):
                    state.category_done = True
                elif not self.run_agent(
                    driver, ctx, f"Ürün için doğru kategoriyi seç ({' > '.join(listing.category_path)}) "
                    "ve ilan detay formuna ulaş.", state
                ):
                    self.ask_human(driver, "Kategori otomatik seçilemedi; lütfen kategoriyi seçin.", state)
                    state.category_done = True
                continue

            self.check_confirmations(driver, snap)
            publish_btn = self.find_publish(snap)
            if publish_btn and not state.publish_clicked:
                self.final_publish(driver, state)
                continue
            cont = self.find_continue(snap)
            if cont:
                self.log(f"➡ '{cont.text}'")
                driver.click(cont.id)
                driver.settle()
                after = driver.snapshot()
                if after.url == snap.url and self.has_listing_form(after) and (after.alerts or any(f.error for f in after.fields)):
                    state.fix_attempts += 1
                    errors = [f"{f.clean_label}: {f.error}" for f in after.fields if f.error][:6]
                    self.log("⚠ Site uyarı verdi: " + ("; ".join(errors) or "; ".join(after.alerts[:3])))
                    if state.fix_attempts <= 2:
                        report.merge(filler.fill(ctx))
                    elif not self.run_agent(driver, ctx, "Formdaki hataları düzelt ve bir sonraki adıma geç "
                                            "(son yayınla düğmesine basma).", state):
                        self.ask_human(driver, "Formda düzeltilemeyen alanlar var: " + "; ".join(errors), state)
                continue
            if state.publish_clicked:
                driver.page.wait_for_timeout(1500)
                continue
            if not self.run_agent(driver, ctx, "İlan verme akışında bir sonraki adıma geç "
                                  "(son yayınla düğmesine basma).", state):
                self.ask_human(driver, "Sonraki adım bulunamadı.", state)
        raise PublishError("İlan verme akışı adım sınırını aştı.")

    # ------------------------------------------------------------ arama

    def search_url(self, query: str = "", url: str = "", price_min: float | None = None,
                   price_max: float | None = None) -> str:
        from urllib.parse import quote_plus

        target = url.strip() or self.ps.search_url_template.format(q=quote_plus(query.strip()))
        params: list[str] = []
        if self.ps.newest_sort_param and self.ps.newest_sort_param.split("=")[0] + "=" not in target:
            params.append(self.ps.newest_sort_param)
        params += self.price_params(target, price_min, price_max)
        if params:
            target += ("&" if "?" in target else "?") + "&".join(params)
        return target

    def price_params(self, url: str, price_min: float | None, price_max: float | None) -> list[str]:
        return []

    def next_page(self, driver: PageDriver, page_no: int) -> bool:
        """Bir sonraki sonuç sayfasına geçer; yoksa False."""
        snap = driver.snapshot()
        btn = snap.find_clickable(["Sonraki", "Sonraki Sayfa", "›", "»", "Daha fazla yükle", "Daha Fazla Göster"],
                                  threshold=0.85)
        if not btn:
            return False
        driver.click(btn.id)
        driver.settle()
        return True


def page_number_param(url: str, key: str, value: int) -> str:
    if re.search(rf"([?&]){key}=\d+", url):
        return re.sub(rf"([?&]){key}=\d+", rf"\g<1>{key}={value}", url)
    return url + ("&" if "?" in url else "?") + f"{key}={value}"
