"""Hesap güvenliği: ilan sınırları, mükerrer ilan koruması, tarama engelinde duraklatma,
taramanın hesaptan ayrı tarayıcı profiliyle yapılması."""

from __future__ import annotations

import http.server
import socketserver
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from autosell.config import Settings
from autosell.db import Database
from autosell.models import Draft, PlatformListing, PublicationStatus, Watch
from autosell.safety import PublishBlocked, check_publish, cooldown, scan_browser, set_cooldown
from autosell.service import AutoSell
from autosell.web import create_app

NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)


def _draft(title: str = "Apple iPhone 13 128 GB Mavi Kutulu") -> Draft:
    return Draft(price=30000, listings={"sahibinden": PlatformListing(title=title, description="x")})


def _log(db: Database, minutes_ago: float, title: str = "Samsung Galaxy S21 Ultra 256 GB") -> None:
    db.log_publish("sahibinden", "eski", title, published_at=(NOW - timedelta(minutes=minutes_ago)).isoformat())


def test_daily_limit_and_min_interval(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = Settings()
    settings.sahibinden.max_publish_per_day = 2
    settings.sahibinden.min_minutes_between_publish = 15
    check_publish(db, settings, _draft(), "sahibinden", now=NOW)  # geçmiş yok: izin var

    _log(db, 5, "PS5 Disk")
    with pytest.raises(PublishBlocked) as exc:
        check_publish(db, settings, _draft(), "sahibinden", now=NOW)
    assert exc.value.code == "too_soon" and "10 dakika" in str(exc.value)

    _log(db, 60 * 3, "Koltuk Takımı")
    with pytest.raises(PublishBlocked) as exc:
        check_publish(db, settings, _draft(), "sahibinden", now=NOW + timedelta(minutes=30), force=True)
    assert exc.value.code == "daily_limit"  # force günlük sınırı geçmez
    check_publish(db, settings, _draft(), "letgo", now=NOW)  # diğer platform etkilenmez


def test_duplicate_and_already_published(tmp_path):
    db = Database(tmp_path / "t.db")
    settings = Settings()
    _log(db, 60 * 24 * 3, "Apple iPhone 13 128GB Mavi Kutulu")
    with pytest.raises(PublishBlocked) as exc:
        check_publish(db, settings, _draft(), "sahibinden", now=NOW)
    assert exc.value.code == "duplicate"
    check_publish(db, settings, _draft(), "sahibinden", now=NOW, force=True)  # farklı ürünse geçilebilir
    check_publish(db, settings, _draft("Sony PlayStation 5 Disk 2 Kollu"), "sahibinden", now=NOW)

    published = _draft("Bambaşka Bir Ürün Başlığı")
    published.publications["sahibinden"] = PublicationStatus(status="yayinda")
    with pytest.raises(PublishBlocked) as exc:
        check_publish(db, settings, published, "sahibinden", now=NOW)
    assert exc.value.code == "already_published"

    old = Database(tmp_path / "o.db")
    old.log_publish("sahibinden", "x", "Apple iPhone 13 128 GB Mavi Kutulu",
                    published_at=(NOW - timedelta(days=45)).isoformat())
    check_publish(old, settings, _draft(), "sahibinden", now=NOW)  # 30 günden eski: sorun yok


def test_cooldown_roundtrip(tmp_path):
    db = Database(tmp_path / "t.db")
    set_cooldown(db, "letgo", 30, "HTTP 429")
    state = cooldown(db, "letgo")
    assert state and state["reason"] == "HTTP 429"
    assert cooldown(db, "letgo", now=datetime.now(timezone.utc) + timedelta(minutes=31)) is None
    assert cooldown(db, "letgo") is None  # süresi dolunca temizlendi


class _Blocking(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(429)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("<h1>Too Many Requests</h1>".encode())

    def log_message(self, *args):
        pass


@pytest.fixture
def blocking_site():
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Blocking)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_blocked_scan_pauses_platform_and_uses_separate_profile(blocking_site, tmp_path):
    app = AutoSell(tmp_path / "veri")
    app.settings_store.update({"browser": {"headless": True, "min_delay_ms": 0, "max_delay_ms": 10}})
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        watch = app.db.save_watch(Watch(name="deneme", platform="letgo", search_url=f"{blocking_site}/arama"))
        job = app.start_scan(watch.id)
        assert job.browser == scan_browser("letgo") == "letgo-tarama"  # hesaptan ayrı profil
        deadline = time.time() + 30
        while job.active and time.time() < deadline:
            time.sleep(0.2)
        assert job.status == "error" and "duraklatıldı" in job.error
        assert (app.paths.browser_dir / "letgo-tarama").exists()
        assert not (app.paths.browser_dir / "letgo").exists()  # hesap profiline hiç dokunulmadı

        status = client.get("/api/status").json()
        assert "letgo" in status["cooldowns"]
        assert watch.id not in app.scheduler.due_watches()
        assert client.post(f"/api/watches/{watch.id}/scan").status_code == 400
        assert client.delete("/api/platforms/letgo/cooldown").json()["ok"]
        assert "letgo" not in client.get("/api/status").json()["cooldowns"]
    finally:
        app.shutdown()


def test_publish_endpoint_returns_409_with_code(tmp_path):
    app = AutoSell(tmp_path / "veri")
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        draft = app.db.save_draft(_draft())
        app.db.log_publish("sahibinden", "eski", "Apple iPhone 13 128GB Mavi Kutulu",
                           published_at=(datetime.now(timezone.utc) - timedelta(days=2)).isoformat())
        r = client.post(f"/api/drafts/{draft.id}/publish", json={"platform": "sahibinden"})
        assert r.status_code == 409 and r.json()["code"] == "duplicate"
    finally:
        app.shutdown()


def test_old_letgo_defaults_are_migrated(tmp_path):
    import json

    from autosell.config import SettingsStore

    path = tmp_path / "ayarlar.json"
    path.write_text(json.dumps({"letgo": {
        "search_url_template": "https://www.letgo.com/arama?q={q}", "newest_sort_param": "",
        "card_selectors": {"card": '[data-aut-id="itemBox"]', "title": '[data-aut-id="itemTitle"]',
                           "price": '[data-aut-id="itemPrice"]', "location": '[data-aut-id="item-location"]',
                           "date": '[data-aut-id="item-date"]', "image": "img"},
        "max_publish_per_day": 3}}), encoding="utf-8")
    letgo = SettingsStore(path).get().letgo
    assert "query_text={q}" in letgo.search_url_template and letgo.newest_sort_param == "sorting=desc-creation"
    assert letgo.card_selectors["card"] == '[data-testid="item-card"]'
    assert letgo.max_publish_per_day == 3  # kullanıcının kendi ayarı korunur

    path.write_text(json.dumps({"letgo": {"search_url_template": "https://ozel/{q}"}}), encoding="utf-8")
    assert SettingsStore(path).get().letgo.search_url_template == "https://ozel/{q}"  # özel ayara dokunulmaz
