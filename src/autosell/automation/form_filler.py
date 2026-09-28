"""Etiket tabanlı genel form doldurucu.

Sayfadaki alanları etiketlerine göre tanır (başlık, açıklama, fiyat, konum,
fotoğraf, kategoriye özel özellikler) ve taslaktaki değerlerle doldurur.
Eşleşmeyen alanlar tek bir yapay zekâ çağrısıyla, sitenin sunduğu seçeneklerle
sınırlı olarak doldurulur. Bağımlı alanlar (İl→İlçe→Mahalle, Marka→Model)
için birkaç tur yapılır.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from playwright.sync_api import Error as PlaywrightError

from ..config import SellerSettings
from ..models import Attribute
from ..textutil import normalize, similarity
from .chooser import ChoiceRequest, Chooser
from .driver import ActionError, Field, PageDriver, is_placeholder, label_score, option_for_value

log = logging.getLogger(__name__)

ROLE_LABELS: dict[str, list[str]] = {
    "title": ["İlan Başlığı", "Başlık", "Ürün Başlığı", "İlan Adı", "Ürün Adı", "Title"],
    "description": ["Açıklama", "İlan Açıklaması", "Ürün Açıklaması", "Detaylı Açıklama", "Description"],
    "price": ["Fiyat", "Satış Fiyatı", "Fiyatı", "Price", "Tutar", "Fiyat (TL)"],
    "currency": ["Para Birimi", "Döviz", "Currency", "Para Cinsi"],
    "city": ["İl", "Şehir", "City"],
    "district": ["İlçe", "District"],
    "neighborhood": ["Mahalle", "Semt", "Mahalle / Köy", "Semt / Mahalle"],
    "location": ["Konum", "Adres", "Lokasyon", "Location", "Konum Seçin", "Bulunduğu Yer"],
    "negotiable": ["Pazarlık payı var", "Pazarlık", "Pazarlığa açık", "Pazarlık Payı"],
}
ROLE_THRESHOLDS = {"city": 0.93, "district": 0.93, "neighborhood": 0.9, "currency": 0.85}
TERMS_WORDS = ("kural", "kabul ediyorum", "okudum", "onayliyorum", "sozlesme", "dogrulugunu", "sartlari")
SENSITIVE_WORDS = (
    "telefon", "gsm", "e posta", "eposta", "email", "e mail", "ad soyad", "adiniz", "isim", "tc kimlik",
    "kimlik no", "iban", "sifre", "parola", "kart", "dogum",
)
SEARCH_TOKENS = frozenset({"ara", "arama", "search", "ariyorsun", "bul"})
CONDITION_OPTIONS = {
    "Sıfır": ["Sıfır", "Yeni", "Sıfır / Yeni", "Etiketli"],
    "Sıfır Ayarında": ["Sıfır Ayarında", "Yeni gibi", "Az Kullanılmış", "Çok İyi", "İkinci El"],
    "Çok İyi": ["Çok İyi", "Yeni gibi", "İyi", "İkinci El", "Kullanılmış"],
    "İyi": ["İyi", "Makul", "İkinci El", "Kullanılmış"],
    "Orta": ["Makul", "Orta", "İyi", "İkinci El", "Kullanılmış"],
    "Kusurlu": ["Kusurlu", "Makul", "Hasarlı", "İkinci El"],
    "Arızalı / Parça": ["Hasarlı/Arızalı", "Arızalı", "Hasarlı", "Parça", "İkinci El"],
}
CONDITION_LABELS = ["Durumu", "Durum", "Ürün Durumu", "Kondisyon", "Kullanım Durumu"]


@dataclass
class FillContext:
    title: str
    description: str
    price: float | None
    currency: str
    attributes: list[Attribute]
    photos: list[Path]
    seller: SellerSettings
    condition: str = ""
    highlights: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class FillReport:
    filled: dict[str, str] = field(default_factory=dict)
    ai_filled: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)
    missing_required: list[str] = field(default_factory=list)
    photos_uploaded: int = 0
    rounds: int = 0

    def merge(self, other: "FillReport") -> None:
        self.filled.update(other.filled)
        self.ai_filled.update(other.ai_filled)
        self.skipped = sorted(set(self.skipped + other.skipped))
        self.missing_required = other.missing_required
        self.photos_uploaded = max(self.photos_uploaded, other.photos_uploaded)
        self.rounds += other.rounds


def format_price(price: float) -> str:
    return str(int(round(price))) if abs(price - round(price)) < 0.005 else f"{price:.2f}".replace(".", ",")


def classify(f: Field) -> str:
    if f.kind == "file":
        return "photos" if ("video" not in f.accept.lower()) else "skip"
    if f.kind in ("password", "search", "email", "tel"):
        return "skip"
    label_n = normalize(f"{f.clean_label} {f.placeholder}")
    if any(w in label_n for w in SENSITIVE_WORDS):
        return "skip"
    if f.kind in ("text", "autocomplete") and any(t in SEARCH_TOKENS for t in label_n.split()):
        return "skip"
    if f.kind == "checkbox":
        text = normalize(f.option_text or f.label)
        if any(w in text for w in TERMS_WORDS):
            return "terms"
        if label_score(f, ROLE_LABELS["negotiable"]) >= 0.8 or "pazarlik" in text:
            return "negotiable"
        return "attr_checkbox"
    scores = {role: label_score(f, names) for role, names in ROLE_LABELS.items() if role != "negotiable"}
    role, score = max(scores.items(), key=lambda kv: kv[1])
    if score >= ROLE_THRESHOLDS.get(role, 0.8):
        if role == "description" and f.kind not in ("textarea", "richtext", "text"):
            return "attribute"
        if role == "title" and f.kind not in ("text", "textarea"):
            return "attribute"
        if role == "price" and f.kind not in ("text", "number"):
            return "attribute"
        return role
    if f.kind == "richtext":
        return "description"
    return "attribute"


class FormFiller:
    def __init__(self, driver: PageDriver, chooser: Chooser, logger: Callable[[str], None] | None = None):
        self.driver = driver
        self.chooser = chooser
        self.say = logger or (lambda m: log.info(m))
        self._photos_done_on: set[str] = set()

    # ------------------------------------------------------------ değer bulma

    def attribute_value(self, f: Field, ctx: FillContext) -> str | None:
        best: tuple[float, Attribute] | None = None
        for attr in ctx.attributes:
            s = label_score(f, [attr.name])
            if s >= 0.8 and (best is None or s > best[0]):
                best = (s, attr)
        if best:
            return best[1].value
        return None

    def _condition_option(self, f: Field, ctx: FillContext, current: str | None) -> str | None:
        if label_score(f, CONDITION_LABELS) < 0.8 or not f.real_options:
            return None
        wanted = ([current] if current else []) + CONDITION_OPTIONS.get(ctx.condition, ["İkinci El", "İyi"])
        for cand in wanted:
            opt = option_for_value(f, cand, threshold=0.85)
            if opt:
                return opt.text
        return None

    # ------------------------------------------------------------ uygulama

    def apply_value(self, f: Field, value: str) -> str | None:
        """Değeri alana yazar/seçer. Başarılıysa gerçekten ayarlanan metni döner."""
        try:
            if f.kind in ("select", "radio"):
                opt = option_for_value(f, value)
                if not opt:
                    return None
                if normalize(f.value) == normalize(opt.text):
                    return opt.text
                self.driver.select_option(f, opt)
                return opt.text
            if f.kind == "combobox":
                if f.value and similarity(f.value, value) >= 0.9:
                    return f.value
                return self.driver.choose_from_popup(f, value)
            if f.kind == "autocomplete":
                return self.driver.choose_from_popup(f, value, type_text=value.split(",")[0].strip())
            if f.kind == "checkbox":
                truthy = normalize(value) in ("evet", "var", "true", "1", "yes", "uygun", "mevcut")
                self.driver.set_checked(f, truthy)
                return "Evet" if truthy else "Hayır"
            if f.kind in ("text", "number", "textarea", "richtext", "date", "url"):
                text = value
                if f.kind == "number":
                    digits = "".join(ch for ch in value if ch.isdigit() or ch in ",.")
                    text = digits.replace(".", "").replace(",", ".") if digits else value
                if normalize(f.value) == normalize(text):
                    return text
                self.driver.fill_text(f, text)
                return text
        except (ActionError, PlaywrightError) as exc:
            self.say(f"'{f.clean_label}' alanı doldurulamadı: {str(exc)[:120]}")
            return None
        return None

    def fill_description(self, f: Field, text: str) -> bool:
        if f.kind != "richtext":
            self.driver.fill_text(f, text)
            return True
        page = self.driver.page
        loc = self.driver.loc(f.id)
        try:
            loc.click(timeout=6000)
            page.keyboard.press("Control+A")
            page.keyboard.press("Delete")
            lines = text.split("\n")
            for i, line in enumerate(lines):
                if line:
                    page.keyboard.insert_text(line)
                if i < len(lines) - 1:
                    page.keyboard.press("Enter")
            written = loc.inner_text(timeout=4000)
        except PlaywrightError as exc:
            self.say(f"Açıklama editörüne yazılamadı: {str(exc)[:120]}")
            written = ""
        probe = normalize(text[:40])
        if probe and probe in normalize(written):
            return True
        # Yedek: HTML olarak yerleştir ve input olayı gönder
        html = "".join(
            "<p>" + "<br>".join(_escape(line) for line in para.split("\n")) + "</p>"
            for para in text.split("\n\n")
        )
        try:
            loc.evaluate(
                "(el, html) => { el.innerHTML = html; el.dispatchEvent(new InputEvent('input', {bubbles: true})); }",
                html,
            )
            return True
        except PlaywrightError:
            return False

    def fill_iframe_editor(self, text: str) -> bool:
        """CKEditor/TinyMCE gibi iframe içindeki editörler için yedek yöntem."""
        for frame in self.driver.page.frames[1:]:
            try:
                body = frame.locator("body[contenteditable=true], body.cke_editable, body#tinymce")
                if body.count() == 0:
                    continue
                body.first.click(timeout=4000)
                self.driver.page.keyboard.press("Control+A")
                self.driver.page.keyboard.insert_text(text)
                return True
            except PlaywrightError:
                continue
        return False

    # ------------------------------------------------------------ ana döngü

    def fill(self, ctx: FillContext, max_rounds: int = 5) -> FillReport:
        report = FillReport()
        handled: set[str] = set()
        ai_asked: set[str] = set()
        seen_description = False
        for round_no in range(1, max_rounds + 1):
            report.rounds = round_no
            snap = self.driver.snapshot()
            pending: list[ChoiceRequest] = []
            progressed = False
            for f in snap.fields:
                key = f"{normalize(f.clean_label)}|{f.kind}|{f.name}" if f.clean_label else f"id:{f.id}"
                if f.disabled or (f.in_chrome and f.kind != "file") or key in handled:
                    continue
                role = classify(f)
                if role == "skip":
                    handled.add(key)
                    continue
                if role == "photos":
                    handled.add(key)
                    page_key = snap.url.split("#")[0]
                    if ctx.photos and page_key not in self._photos_done_on:
                        try:
                            self.driver.upload(f, ctx.photos)
                            self._photos_done_on.add(page_key)
                            report.photos_uploaded = len(ctx.photos) if f.multiple else 1
                            self.say(f"📷 {report.photos_uploaded} fotoğraf yüklendi.")
                            progressed = True
                        except PlaywrightError as exc:
                            self.say(f"Fotoğraf yüklenemedi: {str(exc)[:120]}")
                    continue
                if role == "title":
                    handled.add(key)
                    self._set(report, f, self.apply_value(f, ctx.title))
                    progressed = True
                    continue
                if role == "description":
                    handled.add(key)
                    seen_description = True
                    if normalize(f.value[:60]) != normalize(ctx.description[:60]):
                        if self.fill_description(f, ctx.description):
                            report.filled[f.clean_label or "Açıklama"] = ctx.description[:40] + "…"
                    progressed = True
                    continue
                if role == "price":
                    handled.add(key)
                    if ctx.price is not None:
                        self._set(report, f, self.apply_value(f, format_price(ctx.price)))
                    progressed = True
                    continue
                if role == "currency":
                    handled.add(key)
                    self._set(report, f, self.apply_value(f, "TL") or self.apply_value(f, "Türk Lirası"))
                    continue
                if role in ("city", "district", "neighborhood"):
                    value = {"city": ctx.seller.city, "district": ctx.seller.district,
                             "neighborhood": ctx.seller.neighborhood}[role]
                    if f.kind in ("select", "radio") and not f.real_options:
                        continue  # seçenekler henüz yüklenmedi; sonraki turda
                    handled.add(key)
                    if value:
                        if not self._set(report, f, self.apply_value(f, value)) and f.looks_required:
                            pending.append(ChoiceRequest(f, [o.text for o in f.real_options]))
                        progressed = True
                    elif f.looks_required:
                        self.say(f"⚠ '{f.clean_label}' için Ayarlar > Satıcı bölümünde konum bilgisi girin.")
                    continue
                if role == "location":
                    handled.add(key)
                    loc_value = ", ".join(x for x in (ctx.seller.district, ctx.seller.city) if x)
                    if not loc_value:
                        if f.looks_required:
                            self.say("⚠ Konum için Ayarlar > Satıcı bölümünde il/ilçe girin.")
                        continue
                    chosen: str | None = None
                    try:
                        if f.kind in ("autocomplete", "text"):
                            chosen = self.driver.choose_from_popup(
                                f, loc_value, type_text=ctx.seller.district or ctx.seller.city, threshold=0.55
                            )
                            if chosen is None and f.kind == "text":
                                chosen = self.apply_value(f, loc_value)
                        elif f.kind == "combobox":
                            chosen = self.driver.choose_from_popup(f, loc_value, threshold=0.55)
                        else:
                            chosen = self.apply_value(f, loc_value)
                    except (ActionError, PlaywrightError) as exc:
                        self.say(f"Konum seçilemedi: {str(exc)[:120]}")
                    self._set(report, f, chosen)
                    progressed = True
                    continue
                if role == "negotiable":
                    handled.add(key)
                    self.driver.set_checked(f, ctx.seller.negotiable)
                    report.filled[f.clean_label or "Pazarlık"] = "Evet" if ctx.seller.negotiable else "Hayır"
                    continue
                if role == "terms":
                    handled.add(key)
                    if not f.checked:
                        self.driver.set_checked(f, True)
                        self.say(f"☑ '{(f.option_text or f.label)[:70]}' işaretlendi.")
                    continue
                if role == "attr_checkbox":
                    handled.add(key)
                    self._checkbox_feature(report, f, ctx)
                    continue

                # Kategoriye özel özellik alanı
                if f.kind in ("select", "radio") and not f.real_options:
                    continue  # bağımlı seçenekler yüklenmedi
                value = self.attribute_value(f, ctx)
                applied = self.apply_value(f, value) if value else None
                if not applied and f.kind in ("select", "radio"):
                    cond = self._condition_option(f, ctx, value)
                    applied = self.apply_value(f, cond) if cond else None
                if applied:
                    handled.add(key)
                    self._set(report, f, applied)
                    progressed = True
                    continue
                if not f.is_empty and not f.error:
                    handled.add(key)  # site varsayılanı dolu, dokunma
                    continue
                if key in ai_asked:
                    handled.add(key)
                    continue
                if f.kind in ("select", "radio"):
                    pending.append(ChoiceRequest(f, [o.text for o in f.real_options]))
                elif f.kind == "combobox":
                    pending.append(ChoiceRequest(f, self._read_combobox_options(f)))
                elif f.kind in ("text", "number", "textarea", "autocomplete") and (f.looks_required or value is None):
                    pending.append(ChoiceRequest(f, []))
                ai_asked.add(key)

            if pending and self.chooser.provider:
                self.say(f"🤖 {len(pending)} alan için yapay zekâ değer seçiyor...")
                answers = self.chooser.choose_fields(pending, ctx.summary)
                for req in pending:
                    value = answers.get(req.field.id)
                    if not value:
                        report.skipped.append(req.field.clean_label)
                        continue
                    applied = self.apply_value(req.field, value)
                    if applied:
                        report.ai_filled[req.field.clean_label] = applied
                        progressed = True
            elif pending:
                report.skipped.extend(r.field.clean_label for r in pending)
            self.driver.settle(timeout=3000)
            if not progressed and round_no > 1:
                break

        if not seen_description and ctx.description:
            if self.fill_iframe_editor(ctx.description):
                report.filled["Açıklama"] = ctx.description[:40] + "…"

        final = self.driver.snapshot()
        report.missing_required = [
            f.clean_label or f.name for f in final.fields
            if not f.in_chrome and not f.disabled and f.looks_required and f.is_empty
            and classify(f) not in ("skip", "photos")
        ]
        return report

    # ------------------------------------------------------------ yardımcılar

    def _set(self, report: FillReport, f: Field, value: str | None) -> bool:
        if value:
            report.filled[f.clean_label or f.name or f.id] = value
            return True
        if f.looks_required:
            report.skipped.append(f.clean_label)
        return False

    def _checkbox_feature(self, report: FillReport, f: Field, ctx: FillContext) -> None:
        text = f.option_text or f.label
        if not text:
            return
        value = self.attribute_value(f, ctx)
        if value is not None:
            self._set(report, f, self.apply_value(f, value))
            return
        pool = [a.value for a in ctx.attributes] + [a.name for a in ctx.attributes] + ctx.highlights
        if any(similarity(text, p) >= 0.88 for p in pool if p):
            self.driver.set_checked(f, True)
            report.filled[text[:40]] = "Evet"

    def _read_combobox_options(self, f: Field) -> list[str]:
        try:
            self.driver.loc(f.id).click(timeout=5000)
            self.driver.page.wait_for_timeout(500)
            options = [o.text for o in self.driver.visible_options()]
            self.driver.page.keyboard.press("Escape")
            return [o for o in options if not is_placeholder(o)]
        except PlaywrightError:
            return []


def _escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
