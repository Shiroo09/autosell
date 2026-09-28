"""Kullanıcıyla etkileşim: bilgi mesajları, kullanıcı müdahalesi bekleme ve onay.

Komut satırında ``ConsoleInteraction``, web panelinde ``jobs.JobInteraction``
kullanılır. Bekleme döngüleri tarayıcı iş parçacığında çalışır ve sayfayı
``wait_for_timeout`` ile canlı tutar.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable

from playwright.sync_api import Page


class Cancelled(RuntimeError):
    """Kullanıcı işlemi iptal etti."""


class HumanTimeout(RuntimeError):
    """Kullanıcı müdahalesi zamanında tamamlanmadı."""


class Interaction:
    def log(self, message: str, level: str = "info") -> None:
        print(message)

    def check_cancelled(self) -> None:
        return None

    def attach_screenshot(self, path: Path) -> None:
        return None

    def wait_for_human(self, reason: str, done: Callable[[], bool], page: Page, timeout_s: int) -> None:
        """Kullanıcı tarayıcıda gereken adımı (giriş, CAPTCHA, SMS kodu) yapana kadar bekler."""
        self.log(f"⏳ {reason}", "warning")
        self._set_waiting(reason, "human")
        deadline = time.monotonic() + timeout_s
        try:
            while time.monotonic() < deadline:
                self.check_cancelled()
                page.wait_for_timeout(1500)
                try:
                    if done():
                        self.log("✔ Devam ediliyor.")
                        return
                except Exception:  # sayfa geçişi sırasında okuma hatası olabilir
                    continue
            raise HumanTimeout(f"Zaman aşımı: {reason}")
        finally:
            self._clear_waiting()

    def confirm(self, question: str, page: Page, timeout_s: int, done: Callable[[], bool] | None = None) -> bool | None:
        """Evet/Hayır onayı. Kullanıcı işlemi tarayıcıda kendisi tamamlarsa (done) None döner."""
        raise NotImplementedError

    # Web arayüzü için durum bildirimleri (varsayılan: yok)
    def _set_waiting(self, message: str, kind: str) -> None:
        return None

    def _clear_waiting(self) -> None:
        return None


class ConsoleInteraction(Interaction):
    def __init__(self, auto_yes: bool = False):
        self.auto_yes = auto_yes

    def log(self, message: str, level: str = "info") -> None:
        prefix = {"warning": "! ", "error": "✖ "}.get(level, "")
        print(f"{prefix}{message}", flush=True)

    def confirm(self, question: str, page: Page, timeout_s: int, done: Callable[[], bool] | None = None) -> bool | None:
        if self.auto_yes:
            return True
        answer: list[str] = []
        thread = threading.Thread(
            target=lambda: answer.append(input(f"\n{question} [e/H] (tarayıcıdan kendiniz de yayınlayabilirsiniz): ")),
            daemon=True,
        )
        thread.start()
        deadline = time.monotonic() + timeout_s
        while thread.is_alive() and time.monotonic() < deadline:
            page.wait_for_timeout(700)
            if done:
                try:
                    if done():
                        print("\n✔ İşlemin tarayıcıda tamamlandığı algılandı.")
                        return None
                except Exception:
                    pass
        if not answer:
            return False
        return answer[0].strip().lower() in ("e", "evet", "y", "yes")
