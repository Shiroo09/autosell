"""Hesap güvenliği.

- İlan verme hesabın oturumuyla, tarama/fiyat araştırması ise hiç giriş yapılmamış ayrı
  bir tarayıcı profiliyle yapılır; tarama yüzünden oluşabilecek kısıtlamalar hesabı etkilemez.
- Platform başına 24 saatte en fazla ilan sayısı ve iki ilan arası en az bekleme süresi.
- Aynı ya da çok benzer ilanın kısa sürede tekrar verilmesi (mükerrer ilan) engellenir.
- Site CAPTCHA / erişim engeli gösterirse o platformun taraması bir süre duraklatılır.
- Platform başına saatlik sayfa isteği bütçesi: tarama hızı insan hızını aşmaz.
"""

from __future__ import annotations

import json
import math
import threading
import time
from datetime import datetime, timedelta, timezone

from .config import PLATFORM_NAMES, Settings
from .db import Database
from .models import Draft
from .textutil import similarity

SCAN_SUFFIX = "-tarama"
DUPLICATE_SIMILARITY = 0.9


class PublishBlocked(ValueError):
    """Hesap güvenliği kuralı nedeniyle yayınlama durduruldu."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


class ScanBlocked(RuntimeError):
    """Site taramayı engelledi (CAPTCHA, 403/429, "olağan dışı erişim")."""


def scan_browser(platform: str) -> str:
    """Tarama için kullanılan, giriş yapılmamış tarayıcı profilinin adı."""
    return f"{platform}{SCAN_SUFFIX}"


def _parse(ts: str) -> datetime:
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _local(dt: datetime) -> str:
    return dt.astimezone().strftime("%d.%m %H:%M")


def check_publish(
    db: Database,
    settings: Settings,
    draft: Draft,
    platform: str,
    *,
    force: bool = False,
    now: datetime | None = None,
) -> None:
    """Yayınlamaya izin yoksa PublishBlocked fırlatır. force yalnız mükerrer uyarılarını geçer;
    günlük sınır ve bekleme süresi Ayarlar'dan değiştirilebilir."""
    ps = settings.platform(platform)
    name = PLATFORM_NAMES.get(platform, platform)
    now = now or datetime.now(timezone.utc)

    publication = draft.publications.get(platform)
    if publication and publication.status == "yayinda" and not force:
        raise PublishBlocked(
            f"Bu ilan {name}'de zaten yayınlandı. Aynı ilanı tekrar vermek mükerrer ilan sayılabilir.",
            "already_published",
        )

    window_days = max(1, ps.duplicate_days)
    history = db.publish_history(platform, since=(now - timedelta(days=window_days)).isoformat())
    stamps = [_parse(h["published_at"]) for h in history]

    last_day = [t for t in stamps if t >= now - timedelta(hours=24)]
    if ps.max_publish_per_day > 0 and len(last_day) >= ps.max_publish_per_day:
        free_at = min(last_day) + timedelta(hours=24)
        raise PublishBlocked(
            f"Hesap güvenliği: son 24 saatte {name}'de {len(last_day)} ilan verildi (sınır "
            f"{ps.max_publish_per_day}). Yeni ilan için {_local(free_at)} sonrasını bekleyin ya da "
            "Ayarlar > Platformlar'dan sınırı değiştirin.",
            "daily_limit",
        )

    if stamps and ps.min_minutes_between_publish > 0:
        gap = now - max(stamps)
        needed = timedelta(minutes=ps.min_minutes_between_publish)
        if gap < needed:
            remaining = math.ceil((needed - gap).total_seconds() / 60)
            raise PublishBlocked(
                f"Hesap güvenliği: {name}'de iki ilan arasında en az {ps.min_minutes_between_publish} dakika "
                f"beklenir. Yaklaşık {remaining} dakika sonra tekrar deneyin.",
                "too_soon",
            )

    if not force:
        listing = draft.listings.get(platform)
        title = listing.title if listing else ""
        for entry, stamp in zip(history, stamps):
            if title and similarity(entry["title"], title) >= DUPLICATE_SIMILARITY:
                raise PublishBlocked(
                    f"Mükerrer ilan riski: {_local(stamp)} tarihinde {name}'de benzer bir ilan verildi "
                    f"(\"{entry['title']}\"). Aynı ürünü tekrar ilan etmek kural ihlali sayılabilir. "
                    "Farklı bir ürünse 'Yine de yayınla' seçeneğini kullanın.",
                    "duplicate",
                )


# ------------------------------------------------------------------ tarama soğuma


def _cooldown_key(platform: str) -> str:
    return f"soguma:{platform}"


def set_cooldown(db: Database, platform: str, minutes: int, reason: str) -> datetime:
    until = datetime.now(timezone.utc) + timedelta(minutes=max(1, minutes))
    db.set_state(_cooldown_key(platform), json.dumps({"until": until.isoformat(), "reason": reason[:200]}))
    return until


def clear_cooldown(db: Database, platform: str) -> None:
    db.set_state(_cooldown_key(platform), None)


def cooldown(db: Database, platform: str, now: datetime | None = None) -> dict[str, str] | None:
    raw = db.get_state(_cooldown_key(platform))
    if not raw:
        return None
    data = json.loads(raw)
    until = _parse(data["until"])
    if until <= (now or datetime.now(timezone.utc)):
        clear_cooldown(db, platform)
        return None
    return {"until": data["until"], "until_local": _local(until), "reason": data.get("reason", "")}


# ------------------------------------------------------------ saatlik istek bütçesi

_budget_lock = threading.Lock()


class RequestBudget:
    """Platform başına son bir saatteki sayfa isteklerini (arama + detay) sayar.

    Sınır dolunca yeni taramalar sıraya girer; siteye insan hızından fazla istek gitmez ve
    IP adresiniz "olağan dışı erişim" için işaretlenmez. 0 ya da negatif sınır = sınırsız.
    """

    WINDOW_S = 3600.0

    def __init__(self, db: Database, platform: str, per_hour: int):
        self.db = db
        self.platform = platform
        self.per_hour = per_hour
        self.key = f"istek:{platform}"

    def _stamps(self, now: float) -> list[float]:
        raw = self.db.get_state(self.key)
        try:
            stamps = [float(t) for t in json.loads(raw)] if raw else []
        except (ValueError, TypeError):
            stamps = []
        return sorted(t for t in stamps if now - t < self.WINDOW_S)

    def used(self, now: float | None = None) -> int:
        return len(self._stamps(now if now is not None else time.time()))

    def left(self, now: float | None = None) -> int:
        if self.per_hour <= 0:
            return 1_000_000
        return max(0, self.per_hour - self.used(now))

    def take(self, n: int = 1, now: float | None = None) -> bool:
        """n istek hakkı ayırır; bütçe yetmiyorsa hiçbir şey ayırmadan False döner."""
        now = now if now is not None else time.time()
        with _budget_lock:
            stamps = self._stamps(now)
            if self.per_hour > 0 and len(stamps) + n > self.per_hour:
                return False
            stamps += [now] * n
            self.db.set_state(self.key, json.dumps([round(t, 1) for t in stamps[-max(self.per_hour, 1) - n:]]))
            return True

    def minutes_until(self, n: int = 1, now: float | None = None) -> int:
        """n istek hakkının açılmasına kalan dakika."""
        now = now if now is not None else time.time()
        stamps = self._stamps(now)
        if self.per_hour <= 0 or len(stamps) + n <= self.per_hour:
            return 0
        oldest_needed = stamps[len(stamps) + n - self.per_hour - 1]
        return max(1, math.ceil((oldest_needed + self.WINDOW_S - now) / 60))


def request_budget(db: Database, settings: Settings, platform: str) -> RequestBudget:
    return RequestBudget(db, platform, settings.market.hourly_request_budget)
