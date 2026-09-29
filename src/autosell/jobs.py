"""Arka plan işleri (ilan oluşturma, yayınlama, tarama, giriş) ve canlı günlükleri.

Web paneli işleri başlatır, günlükleri ve "kullanıcı bekleniyor / onay" durumlarını
yoklayarak gösterir. Tarayıcı gerektiren işler ilgili platformun tarayıcı iş
parçacığında, diğerleri bir iş parçacığı havuzunda çalışır.
"""

from __future__ import annotations

import logging
import threading
import time
import traceback
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Page

from .automation.browser import BrowserPool, BrowserSession
from .automation.interaction import Cancelled, Interaction
from .models import new_id, now_iso

log = logging.getLogger(__name__)

JobFn = Callable[["Job", "JobInteraction", "BrowserSession | None"], Any]


@dataclass
class Job:
    kind: str
    title: str
    id: str = field(default_factory=lambda: new_id("is-"))
    status: str = "queued"  # queued | running | waiting | done | error | cancelled
    platform: str | None = None
    browser: str | None = None  # işi yürüten tarayıcı profili (ör. "sahibinden" ya da "sahibinden-tarama")
    draft_id: str | None = None
    watch_id: int | None = None
    created_at: str = field(default_factory=now_iso)
    started_at: str | None = None
    finished_at: str | None = None
    logs: list[dict[str, str]] = field(default_factory=list)
    result: Any = None
    error: str = ""
    prompt: dict[str, str] | None = None
    screenshot: str | None = None
    cancel_requested: bool = False
    response: bool | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_log(self, message: str, level: str = "info") -> None:
        with self._lock:
            self.logs.append({"t": now_iso(), "level": level, "msg": message})
            if len(self.logs) > 800:
                del self.logs[:200]

    @property
    def active(self) -> bool:
        return self.status in ("queued", "running", "waiting")

    def to_dict(self, since: int = 0) -> dict[str, Any]:
        with self._lock:
            logs = self.logs[since:]
            total = len(self.logs)
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "status": self.status,
            "platform": self.platform,
            "browser": self.browser,
            "draft_id": self.draft_id,
            "watch_id": self.watch_id,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "logs": logs,
            "log_count": total,
            "result": self.result,
            "error": self.error,
            "prompt": self.prompt,
            "has_screenshot": bool(self.screenshot),
        }


class JobInteraction(Interaction):
    """Web panelindeki bir işe bağlı kullanıcı etkileşimi."""

    def __init__(self, job: Job):
        self.job = job

    def log(self, message: str, level: str = "info") -> None:
        self.job.add_log(message, level)
        log.info("[%s] %s", self.job.id, message)

    def check_cancelled(self) -> None:
        if self.job.cancel_requested:
            raise Cancelled("İşlem iptal edildi.")

    def attach_screenshot(self, path: Path) -> None:
        self.job.screenshot = str(path)

    def _set_waiting(self, message: str, kind: str) -> None:
        self.job.status = "waiting"
        self.job.prompt = {"type": kind, "message": message}

    def _clear_waiting(self) -> None:
        if self.job.status == "waiting":
            self.job.status = "running"
        self.job.prompt = None

    def confirm(self, question: str, page: Page, timeout_s: int, done: Callable[[], bool] | None = None) -> bool | None:
        self.job.response = None
        self._set_waiting(question, "confirm")
        if self.remote is not None:
            self.remote.activate(question)
        self.log(f"❓ {question} (panelden onaylayın ya da tarayıcıda kendiniz yayınlayın)")
        deadline = time.monotonic() + timeout_s
        try:
            while time.monotonic() < deadline:
                self.check_cancelled()
                if self.job.response is not None:
                    return self.job.response
                self._tick(page, 500)
                if done:
                    try:
                        if done():
                            self.log("✔ Tarayıcıda tamamlandığı algılandı.")
                            return None
                    except Exception:
                        pass
            self.log("Onay zaman aşımına uğradı.", "warning")
            return False
        finally:
            if self.remote is not None:
                self.remote.deactivate()
            self._clear_waiting()


class JobManager:
    def __init__(self, pool: BrowserPool, max_history: int = 150):
        self.pool = pool
        self.max_history = max_history
        self._jobs: "OrderedDict[str, Job]" = OrderedDict()
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="is")

    def submit(self, kind: str, title: str, fn: JobFn, *, browser: str | None = None, **meta: Any) -> Job:
        job = Job(kind=kind, title=title, platform=meta.get("platform") or browser, browser=browser,
                  draft_id=meta.get("draft_id"), watch_id=meta.get("watch_id"))
        with self._lock:
            self._jobs[job.id] = job
            while len(self._jobs) > self.max_history:
                oldest = next(iter(self._jobs))
                if self._jobs[oldest].active:
                    break
                self._jobs.pop(oldest)
        if browser:
            self.pool.worker(browser).submit(lambda session: self._run(job, fn, session), label=title)
        else:
            self._executor.submit(self._run, job, fn, None)
        return job

    def _run(self, job: Job, fn: JobFn, session: BrowserSession | None) -> Any:
        ui = JobInteraction(job)
        if session is not None:
            ui.remote = session.remote
        if job.cancel_requested:
            job.status = "cancelled"
            job.finished_at = now_iso()
            return None
        job.status = "running"
        job.started_at = now_iso()
        try:
            job.result = fn(job, ui, session)
            job.status = "done"
        except Cancelled as exc:
            job.status = "cancelled"
            job.error = str(exc)
            job.add_log(f"⏹ {exc}", "warning")
        except Exception as exc:  # noqa: BLE001 - kullanıcıya gösterilecek
            job.status = "error"
            job.error = str(exc) or exc.__class__.__name__
            job.add_log(f"✖ {job.error}", "error")
            log.warning("İş hatası %s: %s\n%s", job.id, exc, traceback.format_exc())
        finally:
            job.prompt = None
            job.finished_at = now_iso()
        return job.result

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, active_only: bool = False, limit: int = 50) -> list[Job]:
        with self._lock:
            jobs = list(self._jobs.values())
        if active_only:
            jobs = [j for j in jobs if j.active]
        return list(reversed(jobs))[:limit]

    def find_active(self, kind: str, **meta: Any) -> Job | None:
        for job in self.list(active_only=True, limit=500):
            if job.kind == kind and all(getattr(job, k) == v for k, v in meta.items()):
                return job
        return None

    def respond(self, job_id: str, value: bool) -> bool:
        job = self.get(job_id)
        if not job or job.status != "waiting":
            return False
        job.response = value
        return True

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job or not job.active:
            return False
        job.cancel_requested = True
        job.response = False
        if job.status == "queued":
            job.status = "cancelled"
            job.finished_at = now_iso()
        return True

    def shutdown(self) -> None:
        for job in self.list(active_only=True, limit=500):
            job.cancel_requested = True
        self._executor.shutdown(wait=False, cancel_futures=True)
