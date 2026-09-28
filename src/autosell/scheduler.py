"""Takip listelerini ayarlanan aralıklarla otomatik tarayan zamanlayıcı."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .service import AutoSell

log = logging.getLogger(__name__)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class WatchScheduler:
    def __init__(self, app: "AutoSell", tick_seconds: float = 20.0):
        self.app = app
        self.tick_seconds = tick_seconds
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="zamanlayici", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self.tick_seconds):
            try:
                self.tick()
            except Exception:  # noqa: BLE001
                log.exception("Zamanlayıcı hatası")

    def due_watches(self, now: datetime | None = None) -> list[int]:
        now = now or datetime.now(timezone.utc)
        settings = self.app.settings
        due = []
        paused = {p for p in ("sahibinden", "letgo") if self.app.scan_cooldown(p)}
        for watch in self.app.db.list_watches(active_only=True):
            if watch.platform in paused:
                continue
            interval = max(watch.interval_min, settings.market.min_interval_min)
            last = _parse(watch.last_run_at)
            if last and (now - last).total_seconds() < interval * 60:
                continue
            if watch.id is not None:
                due.append(watch.id)
        return due

    def tick(self) -> None:
        for watch_id in self.due_watches():
            if self.app.jobs.find_active("scan", watch_id=watch_id):
                continue
            self.app.start_scan(watch_id, scheduled=True)
