"""Yapay zekâ adım ajanı: sezgisel yöntemler takıldığında sayfayı okuyup tek tek
eylem seçer. Ücretli işlemler, hassas alanlar ve (istenirse) son yayınla
düğmesi kod seviyesinde engellenir."""

from __future__ import annotations

import logging
from typing import Callable

from playwright.sync_api import Error as PlaywrightError

from ..ai.base import AIError, LLMProvider, conform
from ..ai.prompts import AGENT_SYSTEM
from ..ai.schemas import agent_action_schema
from ..textutil import normalize
from .driver import ActionError, PageDriver, Snapshot, option_for_value
from .form_filler import SENSITIVE_WORDS
from .guards import is_payment_page, is_payment_text
from .interaction import Interaction

log = logging.getLogger(__name__)


class AgentResult:
    DONE = "tamam"
    HUMAN = "kullanici"
    PAYMENT = "odeme"
    LIMIT = "limit"
    ERROR = "hata"


class StepAgent:
    def __init__(
        self,
        provider: LLMProvider,
        driver: PageDriver,
        interaction: Interaction,
        max_steps: int = 20,
    ):
        self.provider = provider
        self.driver = driver
        self.interaction = interaction
        self.max_steps = max_steps
        self.last_reason = ""

    def run(
        self,
        goal: str,
        context: str,
        done: Callable[[Snapshot], bool],
        forbidden_click: Callable[[str], bool] | None = None,
    ) -> str:
        schema = agent_action_schema()
        history: list[str] = []
        same_count = 0
        last_sig = ""
        blocked = 0
        for step in range(1, self.max_steps + 1):
            self.interaction.check_cancelled()
            snap = self.driver.snapshot()
            if done(snap):
                return AgentResult.DONE
            if is_payment_page(snap):
                self.last_reason = "Ödeme sayfası algılandı."
                return AgentResult.PAYMENT
            sig = snap.signature()
            same_count = same_count + 1 if sig == last_sig else 0
            last_sig = sig
            if same_count >= 3:
                self.last_reason = "Sayfada ilerleme sağlanamadı."
                return AgentResult.HUMAN

            prompt = (
                f"Hedef: {goal}\n\nİlan bilgileri:\n{context}\n\n"
                f"Şimdiye kadar yapılanlar:\n" + ("\n".join(history[-12:]) or "(henüz yok)") +
                f"\n\nMevcut sayfa:\n{snap.to_prompt()}"
            )
            try:
                action = conform(
                    self.provider.generate_json(system=AGENT_SYSTEM, prompt=prompt, schema=schema, max_tokens=4000),
                    schema,
                )
            except AIError as exc:
                self.last_reason = f"Yapay zekâ hatası: {exc}"
                return AgentResult.ERROR
            kind = action.get("eylem") or "kullanici"
            el_id = (action.get("oge") or "").strip()
            value = action.get("deger") or ""
            why = action.get("aciklama") or ""
            self.interaction.log(f"🤖 Adım {step}: {kind} {el_id} {value[:40]} — {why[:100]}")

            if kind == "tamam":
                if done(self.driver.snapshot()):
                    return AgentResult.DONE
                history.append(f"{step}. 'tamam' dedin ama hedef henüz sağlanmadı.")
                continue
            if kind == "kullanici":
                self.last_reason = why or "Kullanıcı müdahalesi gerekiyor."
                return AgentResult.HUMAN
            if kind == "bekle":
                self.driver.page.wait_for_timeout(1500)
                history.append(f"{step}. bekledi")
                continue

            clickable = next((c for c in snap.clickables if c.id == el_id), None)
            f = snap.field_by_id(el_id)
            if clickable is None and f is None:
                history.append(f"{step}. HATA: '{el_id}' kimlikli öğe yok.")
                continue
            target_text = clickable.text if clickable else (f.option_text or f.clean_label if f else "")
            try:
                if kind == "tikla":
                    if is_payment_text(target_text):
                        blocked += 1
                        history.append(f"{step}. ENGELLENDİ: '{target_text[:40]}' ücretli bir işlem.")
                        if blocked >= 2:
                            self.last_reason = "Devam etmek için ücretli bir adım gerekiyor gibi görünüyor."
                            return AgentResult.PAYMENT
                        continue
                    if forbidden_click and forbidden_click(target_text):
                        # Son yayınla düğmesine gelindi: hedef budur, basmadan dön
                        return AgentResult.DONE
                    self.driver.click(el_id)
                    history.append(f"{step}. '{target_text[:50]}' tıklandı")
                elif f is None:
                    history.append(f"{step}. HATA: '{el_id}' bir form alanı değil.")
                    continue
                elif kind == "yaz":
                    if any(w in normalize(f.clean_label) for w in SENSITIVE_WORDS):
                        history.append(f"{step}. ENGELLENDİ: hassas alana yazılmaz ({f.clean_label}).")
                        continue
                    self.driver.fill_text(f, value)
                    history.append(f"{step}. '{f.clean_label}' alanına '{value[:30]}' yazıldı")
                elif kind == "sec":
                    opt = option_for_value(f, value, threshold=0.6) if f.options else None
                    if opt:
                        self.driver.select_option(f, opt)
                        history.append(f"{step}. '{f.clean_label}' = '{opt.text}' seçildi")
                    else:
                        chosen = self.driver.choose_from_popup(f, value, threshold=0.6)
                        history.append(f"{step}. '{f.clean_label}' = '{chosen or 'seçilemedi'}'")
                elif kind == "isaretle":
                    self.driver.set_checked(f, True)
                    history.append(f"{step}. '{(f.option_text or f.clean_label)[:40]}' işaretlendi")
                self.driver.settle(timeout=5000)
            except (ActionError, PlaywrightError) as exc:
                history.append(f"{step}. HATA: eylem başarısız ({str(exc)[:80]})")
        self.last_reason = "Adım sınırına ulaşıldı."
        return AgentResult.LIMIT
