"""Uzaktan tarayıcı kontrolü.

Otomasyon kullanıcıyı beklerken (giriş, SMS kodu, CAPTCHA, onay) tarayıcı ekranı web
paneline aktarılır; panelden gelen dokunma/yazma komutları tarayıcıda uygulanır. Böylece
AutoSell bir bilgisayarda/sunucuda çalışırken bu adımlar telefondan tamamlanabilir.

Playwright nesneleri tarayıcı iş parçacığına bağlı olduğundan ekran görüntüsü ve
komutlar yalnızca bekleme döngüsü içinde (tarayıcı iş parçacığında) işlenir.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

log = logging.getLogger(__name__)

ALLOWED_KEYS = {"Enter", "Backspace", "Tab", "Escape", "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Delete"}
VIEW_WINDOW_S = 12.0  # son izleme isteğinden sonra ekran görüntüsü alma süresi
FRAME_INTERVAL_S = 0.6


class RemoteControl:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._commands: deque[dict[str, Any]] = deque(maxlen=50)
        self.frame: bytes | None = None
        self.frame_at = 0.0
        self.width = 1366
        self.height = 900
        self.url = ""
        self.title = ""
        self.active = False
        self.reason = ""
        self._viewed_at = 0.0

    # ------------------------------------------------------ web tarafı (herhangi bir iş parçacığı)

    def request_frame(self) -> None:
        self._viewed_at = time.monotonic()

    def push(self, command: dict[str, Any]) -> None:
        kind = command.get("type")
        if kind not in ("click", "type", "key", "scroll"):
            raise ValueError("Geçersiz komut.")
        if kind == "key" and command.get("key") not in ALLOWED_KEYS:
            raise ValueError("Bu tuşa izin verilmiyor.")
        if kind == "type" and len(str(command.get("text", ""))) > 500:
            raise ValueError("Metin çok uzun.")
        with self._lock:
            self._commands.append(command)
        self._viewed_at = time.monotonic()

    def state(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "reason": self.reason,
            "url": self.url,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "frame_age": round(time.monotonic() - self.frame_at, 1) if self.frame else None,
        }

    # ------------------------------------------------------ tarayıcı iş parçacığı

    def activate(self, reason: str) -> None:
        self.active = True
        self.reason = reason

    def deactivate(self) -> None:
        self.active = False
        self.reason = ""
        with self._lock:
            self._commands.clear()

    def service(self, page: Page) -> bool:
        """Bekleyen komutları uygular ve gerekirse ekran görüntüsü alır. Komut uygulandıysa True."""
        acted = False
        while True:
            with self._lock:
                cmd = self._commands.popleft() if self._commands else None
            if cmd is None:
                break
            try:
                self._apply(page, cmd)
                acted = True
            except PlaywrightError as exc:
                log.warning("Uzaktan komut uygulanamadı: %s", exc)
        now = time.monotonic()
        watching = now - self._viewed_at < VIEW_WINDOW_S
        if watching and (acted or now - self.frame_at >= FRAME_INTERVAL_S):
            try:
                size = page.viewport_size or {"width": 1366, "height": 900}
                self.width, self.height = size["width"], size["height"]
                self.frame = page.screenshot(type="jpeg", quality=60, timeout=5000)
                self.frame_at = time.monotonic()
                self.url = page.url
                self.title = page.title()
            except PlaywrightError:
                pass
        return acted

    def _apply(self, page: Page, cmd: dict[str, Any]) -> None:
        kind = cmd["type"]
        size = page.viewport_size or {"width": self.width, "height": self.height}
        if kind == "click":
            x = min(max(float(cmd.get("x", 0)), 0.0), 1.0) * size["width"]
            y = min(max(float(cmd.get("y", 0)), 0.0), 1.0) * size["height"]
            page.mouse.click(x, y)
        elif kind == "type":
            page.keyboard.type(str(cmd.get("text", "")), delay=35)
        elif kind == "key":
            page.keyboard.press(str(cmd["key"]))
        elif kind == "scroll":
            page.mouse.wheel(0, max(-3000, min(3000, int(cmd.get("dy", 400)))))
        page.wait_for_timeout(250)
