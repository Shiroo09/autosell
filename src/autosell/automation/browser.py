"""Platform başına kalıcı (oturumu hatırlayan) Playwright tarayıcısı.

Sync Playwright nesneleri oluşturuldukları iş parçacığına bağlıdır. Bu yüzden her
platformun tarayıcısı kendi iş parçacığında çalışır; ilan verme, tarama ve giriş
işleri bir kuyruk üzerinden sırayla bu iş parçacığında yürütülür.
"""

from __future__ import annotations

import logging
import queue
import threading
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, TypeVar

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from ..config import Settings
from .remote import RemoteControl

log = logging.getLogger(__name__)
T = TypeVar("T")


class BrowserSession:
    """Bir tarayıcı bağlamı ve adlandırılmış sekmeleri."""

    def __init__(self, context: BrowserContext, remote: RemoteControl | None = None):
        self.context = context
        self.remote = remote
        self._pages: dict[str, Page] = {}

    def page(self, name: str = "main", *, close_prefix: str | None = None) -> Page:
        """Adlandırılmış sekmeyi döndürür. close_prefix verilirse aynı önekli eski sekmeler kapatılır
        (ör. her ilan için açılan "ilan-" sekmeleri birikmesin)."""
        if close_prefix:
            for other, pg in list(self._pages.items()):
                if other != name and other.startswith(close_prefix):
                    try:
                        pg.close()
                    except Exception:  # pragma: no cover
                        pass
                    self._pages.pop(other, None)
        page = self._pages.get(name)
        if page is None or page.is_closed():
            used = set(self._pages.values())
            blank = [p for p in self.context.pages if p.url in ("about:blank", "") and p not in used]
            page = blank[0] if blank else self.context.new_page()
            self._pages[name] = page
        try:
            page.bring_to_front()
        except Exception:  # pragma: no cover - görünmez modda önemsiz
            pass
        return page


class BrowserWorker:
    def __init__(self, platform: str, profile_dir: Path, settings_getter: Callable[[], Settings]):
        self.platform = platform
        self.profile_dir = profile_dir
        self.settings_getter = settings_getter
        self._queue: "queue.Queue[tuple[Callable[[BrowserSession], Any], Future[Any], str] | None]" = queue.Queue()
        self._thread = threading.Thread(target=self._run, name=f"tarayici-{platform}", daemon=True)
        self._start_lock = threading.Lock()
        self._started = False
        self._closed_flag = False
        self.current_label: str | None = None
        self.remote = RemoteControl()

    @property
    def busy(self) -> bool:
        return self.current_label is not None

    @property
    def queued(self) -> int:
        return self._queue.qsize()

    def submit(self, fn: Callable[[BrowserSession], T], label: str = "") -> "Future[T]":
        with self._start_lock:
            if not self._started:
                self._thread.start()
                self._started = True
        future: Future[T] = Future()
        self._queue.put((fn, future, label))
        return future

    def run(self, fn: Callable[[BrowserSession], T], label: str = "") -> T:
        return self.submit(fn, label).result()

    def close(self, timeout: float = 15) -> None:
        if self._started:
            self._queue.put(None)
            self._thread.join(timeout=timeout)

    # ------------------------------------------------------------ iş parçacığı

    def _launch(self, pw: Playwright) -> BrowserContext:
        s = self.settings_getter().browser
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        kwargs: dict[str, Any] = {
            "user_data_dir": str(self.profile_dir),
            "headless": s.headless,
            "slow_mo": max(0, s.slow_mo_ms),
            "locale": "tr-TR",
            "timezone_id": "Europe/Istanbul",
            "viewport": {"width": 1366, "height": 900},
            "accept_downloads": False,
        }
        if s.channel:
            kwargs["channel"] = s.channel
        if s.executable_path:
            kwargs["executable_path"] = s.executable_path
        context = pw.chromium.launch_persistent_context(**kwargs)
        self._closed_flag = False
        context.on("close", lambda *_: setattr(self, "_closed_flag", True))
        return context

    def _run(self) -> None:
        pw: Playwright | None = None
        context: BrowserContext | None = None
        session: BrowserSession | None = None
        while True:
            item = self._queue.get()
            if item is None:
                break
            fn, future, label = item
            if not future.set_running_or_notify_cancel():
                continue
            self.current_label = label or "iş"
            try:
                if pw is None:
                    pw = sync_playwright().start()
                if context is None or self._closed_flag:
                    context = self._launch(pw)
                    session = BrowserSession(context, self.remote)
                assert session is not None
                future.set_result(fn(session))
            except BaseException as exc:  # noqa: BLE001 - hatayı çağırana ilet
                future.set_exception(exc)
                if self._closed_flag:
                    context, session = None, None
            finally:
                self.current_label = None
        try:
            if context is not None and not self._closed_flag:
                context.close()
        except Exception:  # pragma: no cover
            pass
        if pw is not None:
            pw.stop()


class BrowserPool:
    def __init__(self, browser_root: Path, settings_getter: Callable[[], Settings]):
        self.browser_root = browser_root
        self.settings_getter = settings_getter
        self._workers: dict[str, BrowserWorker] = {}
        self._lock = threading.Lock()

    def worker(self, platform: str) -> BrowserWorker:
        with self._lock:
            if platform not in self._workers:
                self._workers[platform] = BrowserWorker(
                    platform, self.browser_root / platform, self.settings_getter
                )
            return self._workers[platform]

    def status(self) -> dict[str, dict[str, Any]]:
        with self._lock:
            return {
                name: {"busy": w.busy, "current": w.current_label, "queued": w.queued}
                for name, w in self._workers.items()
            }

    def shutdown(self) -> None:
        with self._lock:
            workers = list(self._workers.values())
            self._workers.clear()
        for w in workers:
            w.close()
