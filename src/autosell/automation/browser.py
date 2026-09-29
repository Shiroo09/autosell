"""Platform başına kalıcı (oturumu hatırlayan) Playwright tarayıcısı.

Sync Playwright nesneleri oluşturuldukları iş parçacığına bağlıdır. Bu yüzden her
platformun tarayıcısı kendi iş parçacığında çalışır; ilan verme, tarama ve giriş
işleri bir kuyruk üzerinden sırayla bu iş parçacığında yürütülür.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import subprocess
import threading
import urllib.request
from concurrent.futures import Future
from pathlib import Path
from typing import Any, Callable, TypeVar

from playwright.sync_api import BrowserContext, Page, Playwright, sync_playwright

from ..config import Settings
from ..safety import SCAN_SUFFIX
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
            "ignore_default_args": ["--enable-automation"],
            "args": ["--disable-blink-features=AutomationControlled"],
        }
        if s.channel:
            kwargs["channel"] = s.channel
        if s.executable_path:
            kwargs["executable_path"] = s.executable_path
        if self.platform.endswith(SCAN_SUFFIX) and self.settings_getter().market.block_images:
            # Tarama profili (hesaptan ayrı, girişsiz) resim/video indirmez: sayfalar çok daha hızlı
            # açılır. İstek yakalama (route) kullanılmaz; o, tarayıcı önbelleğini kapatırdı.
            kwargs["args"] += ["--blink-settings=imagesEnabled=false", "--autoplay-policy=user-gesture-required"]
        if s.channel == "chrome":
            return self._attach_chrome(pw, s.headless, self.profile_dir if self.platform.endswith(SCAN_SUFFIX) else None)
        context = pw.chromium.launch_persistent_context(**kwargs)
        self._closed_flag = False
        context.on("close", lambda *_: setattr(self, "_closed_flag", True))
        return context

    def _attach_chrome(self, pw: Playwright, headless: bool, profile: Path | None = None) -> BrowserContext:
        """Günlük Chrome profiline bağlanır. Playwright'ın eklediği --enable-automation
        bayrağı bu yolda hiç verilmez, o yüzden navigator.webdriver false kalır."""
        src = Path(os.environ["LOCALAPPDATA"]) / "Google" / "Chrome" / "User Data"
        if not (src / "Local State").exists():
            raise RuntimeError("Günlük Chrome profili bulunamadı: " + str(src))
        subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], capture_output=True)
        threading.Event().wait(1.5)
        import shutil
        dst = profile or (self.profile_dir.parent / "chrome-gunluk")
        if profile is None:
            dst.mkdir(parents=True, exist_ok=True)
            if not (dst / "Default" / "Preferences").exists():
                skip = {"Cache", "Code Cache", "GPUCache", "Service Worker", "CacheStorage",
                        "DawnGraphiteCache", "DawnWebGPUCache", "GrShaderCache", "ShaderCache"}
                shutil.copy2(src / "Local State", dst / "Local State")
                shutil.copytree(src / "Default", dst / "Default", dirs_exist_ok=True,
                                ignore=lambda _d, names: [n for n in names if n in skip])
        err = open(self.profile_dir.parent / "_chrome_err.txt", "w", encoding="utf-8")
        flags = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "--remote-debugging-port=9222",
            "--user-data-dir=" + str(dst.resolve()),
            "--profile-directory=Default",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank",
        ]
        if headless:
            flags.insert(-1, "--headless=new")
        self._chrome = subprocess.Popen(flags, stderr=err)
        port = self._wait_port(dst)
        if not port:
            raise RuntimeError("Chrome hata ayıklama kapısını açmadı.")
        info = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5))
        browser = pw.chromium.connect_over_cdp(info["webSocketDebuggerUrl"])
        context = browser.contexts[0]
        self._closed_flag = False
        context.on("close", lambda *_: setattr(self, "_closed_flag", True))
        log.info("Günlük Chrome profiline bağlandı (kapı %s)", port)
        return context
    def _wait_port(self, dst: Path) -> str:
        pause = threading.Event()
        err_path = self.profile_dir.parent / "_chrome_err.txt"
        port_file = dst / "DevToolsActivePort"
        for _ in range(40):
            if port_file.exists():
                line = port_file.read_text(encoding="utf-8").splitlines()
                if line and line[0].strip().isdigit():
                    return line[0].strip()
            text = err_path.read_text(encoding="utf-8", errors="replace") if err_path.exists() else ""
            for line in text.splitlines():
                if "DevTools listening on" in line:
                    return line.split("/devtools/")[0].rsplit(":", 1)[-1]
            if self._chrome.poll() is not None:
                return ""
            pause.wait(0.5)
        return ""

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
