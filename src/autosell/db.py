"""SQLite veri katmanı (taslaklar, takip listeleri, piyasa ilanları, fırsatlar)."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any, Iterable

from .models import Deal, Draft, MarketListing, ScrapedListing, Watch, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS watches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS market_listings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    external_id TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    price REAL,
    currency TEXT NOT NULL DEFAULT 'TL',
    location TEXT NOT NULL DEFAULT '',
    date_text TEXT NOT NULL DEFAULT '',
    image_url TEXT NOT NULL DEFAULT '',
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    seen_count INTEGER NOT NULL DEFAULT 1,
    prev_price REAL,
    details TEXT NOT NULL DEFAULT '{}',
    UNIQUE(platform, external_id)
);
CREATE TABLE IF NOT EXISTS watch_listings (
    watch_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    last_seen TEXT NOT NULL,
    PRIMARY KEY (watch_id, listing_id)
);
CREATE INDEX IF NOT EXISTS idx_watch_listings_seen ON watch_listings(watch_id, last_seen);
CREATE TABLE IF NOT EXISTS price_history (
    listing_id INTEGER NOT NULL,
    price REAL NOT NULL,
    seen_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_price_history ON price_history(listing_id, seen_at);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id INTEGER NOT NULL UNIQUE,
    watch_id INTEGER,
    score REAL NOT NULL DEFAULT 0,
    is_deal INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'yeni',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    data TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_deals_score ON deals(is_deal, status, score);
CREATE TABLE IF NOT EXISTS publish_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    draft_id TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    listing_no TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_publish_log ON publish_log(platform, published_at);
CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_LISTING_COLUMNS = (
    "id, platform, external_id, url, title, price, currency, location, date_text, image_url, "
    "first_seen, last_seen, seen_count, prev_price, details"
)


def _listing_from_row(row: sqlite3.Row) -> MarketListing:
    data = dict(row)
    data["details"] = json.loads(data.get("details") or "{}")
    return MarketListing.model_validate(data)


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def _exec(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self._conn.execute(sql, tuple(params))

    # ---------------------------------------------------------------- taslaklar

    def save_draft(self, draft: Draft) -> Draft:
        draft.updated_at = now_iso()
        self._exec(
            "INSERT INTO drafts(id, created_at, updated_at, data) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET updated_at = excluded.updated_at, data = excluded.data",
            (draft.id, draft.created_at, draft.updated_at, draft.model_dump_json()),
        )
        return draft

    def get_draft(self, draft_id: str) -> Draft | None:
        rows = self._query("SELECT data FROM drafts WHERE id = ?", (draft_id,))
        return Draft.model_validate_json(rows[0]["data"]) if rows else None

    def list_drafts(self) -> list[Draft]:
        rows = self._query("SELECT data FROM drafts ORDER BY updated_at DESC")
        return [Draft.model_validate_json(r["data"]) for r in rows]

    def delete_draft(self, draft_id: str) -> None:
        self._exec("DELETE FROM drafts WHERE id = ?", (draft_id,))

    # ---------------------------------------------------------- takip listeleri

    def save_watch(self, watch: Watch) -> Watch:
        payload = watch.model_dump_json(exclude={"id"})
        with self._lock:
            if watch.id is None:
                cur = self._conn.execute(
                    "INSERT INTO watches(active, created_at, data) VALUES (?, ?, ?)",
                    (int(watch.active), watch.created_at, payload),
                )
                watch.id = int(cur.lastrowid)
            else:
                self._conn.execute(
                    "UPDATE watches SET active = ?, data = ? WHERE id = ?",
                    (int(watch.active), payload, watch.id),
                )
        return watch

    def get_watch(self, watch_id: int) -> Watch | None:
        rows = self._query("SELECT id, data FROM watches WHERE id = ?", (watch_id,))
        if not rows:
            return None
        return Watch.model_validate({**json.loads(rows[0]["data"]), "id": rows[0]["id"]})

    def list_watches(self, active_only: bool = False) -> list[Watch]:
        sql = "SELECT id, data FROM watches"
        if active_only:
            sql += " WHERE active = 1"
        rows = self._query(sql + " ORDER BY id")
        return [Watch.model_validate({**json.loads(r["data"]), "id": r["id"]}) for r in rows]

    def delete_watch(self, watch_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM watches WHERE id = ?", (watch_id,))
            self._conn.execute("DELETE FROM watch_listings WHERE watch_id = ?", (watch_id,))

    # ---------------------------------------------------------- piyasa ilanları

    def upsert_listing(
        self, item: ScrapedListing, watch_id: int | None = None, seen_at: str | None = None
    ) -> tuple[MarketListing, str]:
        """İlanı ekler/günceller. Dönüş: (ilan, "new" | "price_changed" | "seen")."""
        seen_at = seen_at or now_iso()
        with self._lock:
            rows = self._conn.execute(
                f"SELECT {_LISTING_COLUMNS} FROM market_listings WHERE platform = ? AND external_id = ?",
                (item.platform, item.external_id),
            ).fetchall()
            if not rows:
                cur = self._conn.execute(
                    "INSERT INTO market_listings(platform, external_id, url, title, price, currency, "
                    "location, date_text, image_url, first_seen, last_seen) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item.platform, item.external_id, item.url, item.title, item.price,
                        item.currency, item.location, item.date_text, item.image_url, seen_at, seen_at,
                    ),
                )
                listing_id = int(cur.lastrowid)
                if item.price is not None:
                    self._conn.execute(
                        "INSERT INTO price_history(listing_id, price, seen_at) VALUES (?, ?, ?)",
                        (listing_id, item.price, seen_at),
                    )
                change = "new"
            else:
                old = _listing_from_row(rows[0])
                listing_id = old.id
                price_changed = (
                    item.price is not None and old.price is not None and abs(item.price - old.price) >= 1
                )
                self._conn.execute(
                    "UPDATE market_listings SET url = ?, title = ?, price = COALESCE(?, price), "
                    "currency = ?, location = COALESCE(NULLIF(?, ''), location), "
                    "date_text = COALESCE(NULLIF(?, ''), date_text), "
                    "image_url = COALESCE(NULLIF(?, ''), image_url), last_seen = ?, "
                    "seen_count = seen_count + 1, prev_price = ? WHERE id = ?",
                    (
                        item.url or old.url, item.title or old.title, item.price, item.currency,
                        item.location, item.date_text, item.image_url, seen_at,
                        old.price if price_changed else old.prev_price, listing_id,
                    ),
                )
                if price_changed:
                    self._conn.execute(
                        "INSERT INTO price_history(listing_id, price, seen_at) VALUES (?, ?, ?)",
                        (listing_id, item.price, seen_at),
                    )
                change = "price_changed" if price_changed else "seen"
            if watch_id is not None:
                self._conn.execute(
                    "INSERT INTO watch_listings(watch_id, listing_id, last_seen) VALUES (?, ?, ?) "
                    "ON CONFLICT(watch_id, listing_id) DO UPDATE SET last_seen = excluded.last_seen",
                    (watch_id, listing_id, seen_at),
                )
            listing = self.get_listing(listing_id)
        assert listing is not None
        return listing, change

    def get_listing(self, listing_id: int) -> MarketListing | None:
        rows = self._query(f"SELECT {_LISTING_COLUMNS} FROM market_listings WHERE id = ?", (listing_id,))
        return _listing_from_row(rows[0]) if rows else None

    def listings_for_watch(self, watch_id: int, since: str | None = None) -> list[MarketListing]:
        sql = (
            f"SELECT {', '.join('m.' + c.strip() for c in _LISTING_COLUMNS.split(','))} "
            "FROM market_listings m JOIN watch_listings w ON w.listing_id = m.id WHERE w.watch_id = ?"
        )
        params: list[Any] = [watch_id]
        if since:
            sql += " AND w.last_seen >= ?"
            params.append(since)
        return [_listing_from_row(r) for r in self._query(sql + " ORDER BY m.last_seen DESC", params)]

    def listings_for_platform(self, platform: str, since: str | None = None) -> list[MarketListing]:
        sql = f"SELECT {_LISTING_COLUMNS} FROM market_listings WHERE platform = ?"
        params: list[Any] = [platform]
        if since:
            sql += " AND last_seen >= ?"
            params.append(since)
        return [_listing_from_row(r) for r in self._query(sql + " ORDER BY last_seen DESC", params)]

    def set_listing_details(self, listing_id: int, details: dict[str, Any]) -> None:
        self._exec(
            "UPDATE market_listings SET details = ? WHERE id = ?",
            (json.dumps(details, ensure_ascii=False), listing_id),
        )

    def price_history(self, listing_id: int) -> list[dict[str, Any]]:
        rows = self._query(
            "SELECT price, seen_at FROM price_history WHERE listing_id = ? ORDER BY seen_at", (listing_id,)
        )
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------ fırsatlar

    def save_deal(self, deal: Deal) -> Deal:
        with self._lock:
            existing = self.get_deal_by_listing(deal.listing_id)
            if existing:
                deal.id = existing.id
                deal.created_at = existing.created_at
                deal.notified = deal.notified or existing.notified
                if existing.status != "yeni" and deal.status == "yeni":
                    deal.status = existing.status
            deal.updated_at = now_iso()
            payload = deal.model_dump_json(exclude={"id"})
            if deal.id is None:
                cur = self._conn.execute(
                    "INSERT INTO deals(listing_id, watch_id, score, is_deal, status, created_at, updated_at, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        deal.listing_id, deal.watch_id, deal.score, int(deal.is_deal), deal.status,
                        deal.created_at, deal.updated_at, payload,
                    ),
                )
                deal.id = int(cur.lastrowid)
            else:
                self._conn.execute(
                    "UPDATE deals SET watch_id = ?, score = ?, is_deal = ?, status = ?, updated_at = ?, data = ? "
                    "WHERE id = ?",
                    (
                        deal.watch_id, deal.score, int(deal.is_deal), deal.status, deal.updated_at,
                        payload, deal.id,
                    ),
                )
        return deal

    def _deal_from_row(self, row: sqlite3.Row) -> Deal:
        return Deal.model_validate({**json.loads(row["data"]), "id": row["id"], "status": row["status"]})

    def get_deal(self, deal_id: int) -> Deal | None:
        rows = self._query("SELECT id, status, data FROM deals WHERE id = ?", (deal_id,))
        return self._deal_from_row(rows[0]) if rows else None

    def get_deal_by_listing(self, listing_id: int) -> Deal | None:
        rows = self._query("SELECT id, status, data FROM deals WHERE listing_id = ?", (listing_id,))
        return self._deal_from_row(rows[0]) if rows else None

    def list_deals(
        self,
        *,
        status: str | None = None,
        min_score: float | None = None,
        watch_id: int | None = None,
        only_deals: bool = True,
        limit: int = 200,
    ) -> list[tuple[Deal, MarketListing]]:
        sql = "SELECT d.id, d.status, d.data, d.listing_id FROM deals d WHERE 1 = 1"
        params: list[Any] = []
        if only_deals:
            sql += " AND d.is_deal = 1"
        if status:
            sql += " AND d.status = ?"
            params.append(status)
        else:
            sql += " AND d.status != 'gizli'"
        if min_score is not None:
            sql += " AND d.score >= ?"
            params.append(min_score)
        if watch_id is not None:
            sql += " AND d.watch_id = ?"
            params.append(watch_id)
        sql += " ORDER BY d.score DESC, d.updated_at DESC LIMIT ?"
        params.append(limit)
        out: list[tuple[Deal, MarketListing]] = []
        for row in self._query(sql, params):
            listing = self.get_listing(row["listing_id"])
            if listing:
                out.append((self._deal_from_row(row), listing))
        return out

    def set_deal_status(self, deal_id: int, status: str) -> Deal | None:
        deal = self.get_deal(deal_id)
        if not deal:
            return None
        deal.status = status  # type: ignore[assignment]
        deal.updated_at = now_iso()
        self._exec(
            "UPDATE deals SET status = ?, updated_at = ?, data = ? WHERE id = ?",
            (status, deal.updated_at, deal.model_dump_json(exclude={"id"}), deal_id),
        )
        return deal

    # ----------------------------------------------------------- yayın kaydı

    def log_publish(self, platform: str, draft_id: str, title: str, url: str = "", listing_no: str = "",
                    published_at: str | None = None) -> None:
        self._exec(
            "INSERT INTO publish_log(platform, draft_id, title, url, listing_no, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (platform, draft_id, title, url, listing_no, published_at or now_iso()),
        )

    def publish_history(self, platform: str, since: str | None = None) -> list[dict[str, Any]]:
        sql = "SELECT platform, draft_id, title, url, listing_no, published_at FROM publish_log WHERE platform = ?"
        params: list[Any] = [platform]
        if since:
            sql += " AND published_at >= ?"
            params.append(since)
        return [dict(r) for r in self._query(sql + " ORDER BY published_at DESC", params)]

    # ------------------------------------------------------- basit durum deposu

    def set_state(self, key: str, value: str | None) -> None:
        if value is None:
            self._exec("DELETE FROM kv WHERE key = ?", (key,))
        else:
            self._exec(
                "INSERT INTO kv(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def get_state(self, key: str) -> str | None:
        rows = self._query("SELECT value FROM kv WHERE key = ?", (key,))
        return rows[0]["value"] if rows else None

    # --------------------------------------------------------------- istatistik

    def stats(self) -> dict[str, Any]:
        def scalar(sql: str, params: Iterable[Any] = ()) -> int:
            return int(self._query(sql, params)[0][0] or 0)

        drafts = self.list_drafts()
        published = sum(
            1 for d in drafts for p in d.publications.values() if p.status == "yayinda"
        )
        today = now_iso()[:10]
        return {
            "drafts": len(drafts),
            "published": published,
            "watches": scalar("SELECT COUNT(*) FROM watches"),
            "active_watches": scalar("SELECT COUNT(*) FROM watches WHERE active = 1"),
            "market_listings": scalar("SELECT COUNT(*) FROM market_listings"),
            "deals": scalar("SELECT COUNT(*) FROM deals WHERE is_deal = 1 AND status != 'gizli'"),
            "deals_today": scalar(
                "SELECT COUNT(*) FROM deals WHERE is_deal = 1 AND status != 'gizli' AND created_at >= ?",
                (today,),
            ),
        }
