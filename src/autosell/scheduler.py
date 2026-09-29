"""Takip listelerini ayarlanan aralıklarla otomatik tarayan zamanlayıcı."""

from __future__ import annotations

import logging
import random
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .config import PLATFORMS
from .safety import request_budget

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
    def __init__(self, app: "AutoSell", tick_seconds: float = 10.0):
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
        market = settings.market
        due = []
        paused = {p for p in PLATFORMS if self.app.scan_cooldown(p)}
        # Arama sayfası + detay sayfaları için bütçe kalmadıysa o platform bekler
        starved = set()
        for p in PLATFORMS:
            budget = request_budget(self.app.db, settings, p)
            need = 1 + max(0, market.fetch_details)
            if budget.per_hour > 0:
                need = max(1, min(need, budget.per_hour))
            if budget.left() < need:
                starved.add(p)
        for watch in self.app.db.list_watches(active_only=True):
            if watch.platform in paused or watch.platform in starved:
                continue
            interval = max(watch.interval_min, market.min_interval_min) * 60
            last = _parse(watch.last_run_at)
            if last:
                # Her tarama sonrası sabit (tekrarlanabilir) bir rastgele kayma: istekler dakika
                # dakika aynı düzende gitmez.
                spread = max(0.0, min(market.interval_jitter_pct, 50.0)) / 100
                jitter = random.Random(f"{watch.id}:{watch.last_run_at}").uniform(-spread, spread)
                if (now - last).total_seconds() < interval * (1 + jitter):
                    continue
            if watch.id is not None:
                due.append(watch.id)
        return due

    def tick(self) -> None:
        for watch_id in self.due_watches():
            if self.app.jobs.find_active("scan", watch_id=watch_id):
                continue
            try:
                self.app.start_scan(watch_id, scheduled=True)
            except (ValueError, KeyError) as exc:  # duraklatma / bütçe / silinmiş takip
                log.info("Tarama başlatılmadı (%s): %s", watch_id, exc)
