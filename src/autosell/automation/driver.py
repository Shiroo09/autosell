"""Sayfa anlık görüntüsü (snapshot) modelleri ve tarayıcı eylemleri."""

from __future__ import annotations

import hashlib
import logging
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Locator, Page
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from ..config import BrowserSettings
from ..textutil import best_match, normalize, similarity
from .snapshot_js import COOKIE_BANNER_JS, SNAPSHOT_JS, VISIBLE_OPTIONS_JS

log = logging.getLogger(__name__)

PLACEHOLDER_VALUES = {"", "seciniz", "secin", "lutfen seciniz", "lutfen secin", "sec", "seçiniz", "-", "--",
                      "select", "choose", "hepsi", "tumu", "secim yapiniz"}


def is_placeholder(value: str) -> bool:
    n = normalize(value)
    return n in PLACEHOLDER_VALUES or n.startswith("secin") or n.startswith("lutfen sec")


@dataclass
class Option:
    text: str
    value: str = ""
    id: str = ""
    input_id: str = ""
    selected: bool = False
    disabled: bool = False


@dataclass
class Field:
    id: str
    kind: str
    label: str = ""
    tag: str = ""
    type: str = ""
    role: str = ""
    name: str = ""
    placeholder: str = ""
    required: bool = False
    disabled: bool = False
    in_chrome: bool = False
    hidden: bool = False
    maxlength: int | None = None
    autocomplete: str = ""
    value: str = ""
    selected_value: str = ""
    checked: bool = False
    option_text: str = ""
    error: str = ""
    multiple: bool = False
    accept: str = ""
    options: list[Option] = field(default_factory=list)

    @property
    def clean_label(self) -> str:
        label = re.sub(r"[*:]+", " ", self.label)
        label = re.sub(r"\((zorunlu|isteğe bağlı|opsiyonel)\)", " ", label, flags=re.IGNORECASE)
        return re.sub(r"\s+", " ", label).strip()

    @property
    def looks_required(self) -> bool:
        return self.required or "*" in self.label or bool(self.error)

    @property
    def is_empty(self) -> bool:
        if self.kind == "checkbox":
            return not self.checked
        if self.kind in ("select", "radio", "combobox"):
            return is_placeholder(self.value) or not self.value
        return not self.value.strip()

    @property
    def real_options(self) -> list[Option]:
        return [o for o in self.options if not o.disabled and not is_placeholder(o.text)]


@dataclass
class Clickable:
    id: str
    text: str
    tag: str = ""
    role: str = ""
    href: str = ""
    disabled: bool = False
    selected: bool = False
    in_chrome: bool = False
    fixed: bool = False
    x: int = 0
    y: int = 0


@dataclass
class Snapshot:
    url: str
    title: str
    fields: list[Field]
    clickables: list[Clickable]
    text: str
    alerts: list[str]
    frames: list[str]

    @classmethod
    def from_js(cls, data: dict[str, Any]) -> "Snapshot":
        fields = []
        for raw in data.get("fields", []):
            opts = [Option(**{k: o.get(k) for k in ("text", "value", "id", "input_id", "selected", "disabled") if o.get(k) is not None})
                    for o in raw.get("options", [])]
            known = {k: raw[k] for k in Field.__dataclass_fields__ if k in raw and k != "options"}
            fields.append(Field(**known, options=opts))
        clickables = [
            Clickable(**{k: c[k] for k in Clickable.__dataclass_fields__ if k in c}) for c in data.get("clickables", [])
        ]
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            fields=fields,
            clickables=clickables,
            text=data.get("text", ""),
            alerts=data.get("alerts", []),
            frames=data.get("frames", []),
        )

    @property
    def norm_text(self) -> str:
        return normalize(self.text)

    def signature(self) -> str:
        parts = [self.url] + [f"{f.id}:{f.value}:{f.checked}" for f in self.fields]
        parts += [c.text for c in self.clickables[:200]]
        return hashlib.sha1("|".join(parts).encode()).hexdigest()

    def field_by_id(self, el_id: str) -> Field | None:
        return next((f for f in self.fields if f.id == el_id), None)

    def find_clickable(
        self,
        texts: list[str],
        threshold: float = 0.85,
        *,
        include_chrome: bool = False,
        enabled_only: bool = True,
        exclude: Callable[[Clickable], bool] | None = None,
    ) -> Clickable | None:
        best: tuple[float, Clickable] | None = None
        for c in self.clickables:
            if (c.in_chrome and not include_chrome) or (enabled_only and c.disabled):
                continue
            if exclude and exclude(c):
                continue
            score = max((similarity(c.text, t) for t in texts), default=0.0)
            if score >= threshold and (best is None or score > best[0]):
                best = (score, c)
        return best[1] if best else None

    def to_prompt(self, max_fields: int = 80, max_clickables: int = 160) -> str:
        lines = [f"URL: {self.url}", f"Sayfa başlığı: {self.title}"]
        if self.alerts:
            lines.append("Uyarılar: " + " | ".join(self.alerts[:8]))
        lines.append("Form alanları:")
        for f in self.fields[:max_fields]:
            if f.in_chrome:
                continue
            desc = f"- [{f.id}] {f.kind} '{f.clean_label}'"
            if f.required:
                desc += " (zorunlu)"
            if f.kind in ("select", "radio") and f.options:
                opts = ", ".join(o.text for o in f.options[:25])
                desc += f" seçenekler: {opts}{' ...' if len(f.options) > 25 else ''}"
            if f.kind == "checkbox":
                desc += f" işaretli={f.checked}"
            elif f.value:
                desc += f" değer='{f.value[:60]}'"
            if f.error:
                desc += f" HATA: {f.error[:80]}"
            lines.append(desc)
        lines.append("Tıklanabilir öğeler:")
        for c in self.clickables[:max_clickables]:
            flags = []
            if c.disabled:
                flags.append("pasif")
            if c.selected:
                flags.append("seçili")
            if c.in_chrome:
                flags.append("menü")
            lines.append(f"- [{c.id}] {c.tag} '{c.text[:70]}'" + (f" ({', '.join(flags)})" if flags else ""))
        lines.append("Sayfa metni (ilk kısım): " + self.text[:1500])
        return "\n".join(lines)


class ActionError(RuntimeError):
    pass


class PageDriver:
    """Tek bir sayfa üzerinde snapshot alma ve insan hızında eylem yapma."""

    def __init__(self, page: Page, settings: BrowserSettings, logger: Callable[[str], None] | None = None):
        self.page = page
        self.settings = settings
        self.say = logger or (lambda msg: log.info(msg))

    # ------------------------------------------------------------- yardımcılar

    def pause(self, factor: float = 1.0) -> None:
        lo, hi = sorted((max(0, self.settings.min_delay_ms), max(0, self.settings.max_delay_ms)))
        self.page.wait_for_timeout(int(random.uniform(lo, hi) * factor))

    def settle(self, timeout: int = 8000) -> None:
        try:
            self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except PlaywrightTimeout:
            pass
        try:
            self.page.wait_for_load_state("networkidle", timeout=min(timeout, 4000))
        except PlaywrightTimeout:
            pass
        self.page.wait_for_timeout(350)

    def goto(self, url: str) -> None:
        self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.settle()
        self.dismiss_cookie_banner()

    def snapshot(self) -> Snapshot:
        last_exc: Exception | None = None
        for _ in range(3):
            try:
                return Snapshot.from_js(self.page.evaluate(SNAPSHOT_JS, {"maxClickables": 500}))
            except PlaywrightError as exc:  # gezinme sırasında bağlam yok olabilir
                last_exc = exc
                self.page.wait_for_timeout(700)
        raise ActionError(f"Sayfa okunamadı: {last_exc}")

    def dismiss_cookie_banner(self) -> bool:
        try:
            clicked = self.page.evaluate(COOKIE_BANNER_JS)
        except PlaywrightError:
            return False
        if clicked:
            self.say(f"Çerez bildirimi kapatıldı ({clicked}).")
            self.page.wait_for_timeout(300)
            return True
        return False

    def loc(self, el_id: str) -> Locator:
        return self.page.locator(f'[data-as-id="{el_id}"]').first

    def screenshot(self, path: Path) -> Path | None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.page.screenshot(path=str(path), full_page=True)
            return path
        except PlaywrightError:
            return None

    # ------------------------------------------------------------------ eylemler

    def click(self, el_id: str, *, timeout: int = 8000) -> None:
        loc = self.loc(el_id)
        self.pause(0.6)
        try:
            loc.scroll_into_view_if_needed(timeout=timeout)
            loc.click(timeout=timeout)
        except PlaywrightError as exc:
            # Üstte kalan katman (çerez bandı vb.) tıklamayı engelliyor olabilir
            if self.dismiss_cookie_banner():
                try:
                    loc.click(timeout=timeout)
                    return
                except PlaywrightError:
                    pass
            try:
                loc.evaluate("el => el.click()")
            except PlaywrightError:
                raise ActionError(f"Tıklanamadı ({el_id}): {exc}") from exc

    def fill_text(self, f: Field, text: str) -> None:
        if f.maxlength:
            text = text[: f.maxlength]
        loc = self.loc(f.id)
        self.pause(0.5)
        try:
            loc.scroll_into_view_if_needed(timeout=5000)
        except PlaywrightError:
            pass
        try:
            loc.fill(text, timeout=8000)
        except PlaywrightError:
            loc.click(timeout=5000)
            self.page.keyboard.press("Control+A")
            self.page.keyboard.insert_text(text)
        try:  # bazı formlar doğrulamayı blur ile yapar
            loc.evaluate("el => { el.dispatchEvent(new Event('change', {bubbles: true})); el.blur && el.blur(); }")
        except PlaywrightError:
            pass

    def select_option(self, f: Field, option: Option) -> None:
        self.pause(0.5)
        if f.kind == "select":
            loc = self.loc(f.id)
            try:
                if option.value:
                    loc.select_option(value=option.value, timeout=8000)
                else:
                    loc.select_option(label=option.text, timeout=8000)
            except PlaywrightError as exc:
                raise ActionError(f"Seçilemedi ({f.clean_label} = {option.text}): {exc}") from exc
            return
        if f.kind == "radio":
            target = option.id or option.input_id
            try:
                self.loc(target).click(timeout=6000)
            except PlaywrightError:
                if option.input_id:
                    self.loc(option.input_id).check(force=True, timeout=6000)
                else:
                    raise
            return
        raise ActionError(f"Desteklenmeyen seçim alanı: {f.kind}")

    def visible_options(self) -> list[Option]:
        try:
            raw = self.page.evaluate(VISIBLE_OPTIONS_JS)
        except PlaywrightError:
            return []
        return [Option(text=o["text"], id=o["id"]) for o in raw]

    def choose_from_popup(self, f: Field, value: str, *, type_text: str | None = None, threshold: float = 0.7) -> str | None:
        """Özel açılır listeler (combobox) ve otomatik tamamlamalı alanlar için seçim yapar."""
        loc = self.loc(f.id)
        before = {o.id for o in self.visible_options()}
        self.pause(0.5)
        if f.kind == "autocomplete" or type_text:
            text = type_text or value
            loc.click(timeout=6000)
            loc.fill("", timeout=6000)
            loc.press_sequentially(text, delay=60)
        else:
            loc.click(timeout=6000)
        options: list[Option] = []
        for _ in range(12):
            self.page.wait_for_timeout(250)
            options = self.visible_options()
            fresh = [o for o in options if o.id not in before]
            if fresh:
                options = fresh
                break
            if options and f.kind != "autocomplete":
                break
        if not options:
            try:
                self.page.keyboard.press("Escape")
            except PlaywrightError:
                pass
            return None
        idx, score = best_match(value, [o.text for o in options])
        if idx < 0 or score < threshold:
            try:
                self.page.keyboard.press("Escape")
            except PlaywrightError:
                pass
            return None
        chosen = options[idx]
        self.loc(chosen.id).click(timeout=6000)
        return chosen.text

    def set_checked(self, f: Field, checked: bool) -> None:
        if f.checked == checked:
            return
        loc = self.loc(f.id)
        self.pause(0.4)
        try:
            if f.role == "switch":
                loc.click(timeout=6000)
            elif checked:
                loc.check(timeout=6000)
            else:
                loc.uncheck(timeout=6000)
        except PlaywrightError:
            try:
                loc.check(force=True, timeout=4000) if checked else loc.uncheck(force=True, timeout=4000)
            except PlaywrightError:
                loc.evaluate("(el, v) => { if (el.checked !== v) el.click(); }", checked)

    def upload(self, f: Field, files: list[Path]) -> None:
        paths = [str(p) for p in files]
        if not f.multiple:
            paths = paths[:1]
        self.loc(f.id).set_input_files(paths, timeout=15000)
        self.page.wait_for_timeout(800 + 250 * len(paths))


def option_for_value(f: Field, value: str, threshold: float = 0.72) -> Option | None:
    options = f.real_options
    if not options or not value:
        return None
    idx, score = best_match(value, [o.text for o in options])
    if idx >= 0 and score >= threshold:
        return options[idx]
    # Sayısal değerlerde sayı eşleşmesi ("128 GB" -> "128 GB Dahili Hafıza")
    digits = re.findall(r"\d+", value)
    if digits:
        for o in options:
            if re.findall(r"\d+", o.text)[:len(digits)] == digits and similarity(value, o.text) >= 0.5:
                return o
    return None


def label_score(f: Field, names: list[str]) -> float:
    candidates = [f.clean_label, f.placeholder, f.name.replace("_", " ")]
    return max((similarity(c, n) for c in candidates if c for n in names), default=0.0)
