"""Hızlı karar motoru (Jev / Laya) ve hızlı tarama: eleme kararları, protokol istemcisi,
artımlı sayfa okuma ve saatlik istek bütçesi."""

from __future__ import annotations

import functools
import http.server
import json
import socketserver
import threading
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from autosell.ai.decision import DecisionEngine, DecisionError, systemone_url
from autosell.automation.browser import BrowserPool
from autosell.config import Settings
from autosell.db import Database
from autosell.market.fastcheck import LISTING_QUESTIONS, apply_decision
from autosell.market.scanner import MarketScanner
from autosell.models import Deal, Watch
from autosell.safety import RequestBudget
from autosell.service import AutoSell
from autosell.web import create_app

from .test_flow import ScriptedInteraction
from .test_scan import _search_html


def _cevap(olumlu: str, diger: str, olasilik: float) -> dict:
    return {"type": "choice", "choice": olumlu if olasilik >= 0.5 else diger,
            "probabilities": {olumlu: olasilik, diger: round(1 - olasilik, 4)}}


def _answers(kind="urun", same=0.95, faulty=0.03, shady=0.05):
    return {
        "ilan_turu": {"type": "choice", "choice": kind, "confidence": 1, "probabilities": {kind: 0.97}},
        "ayni_urun": _cevap("ayni", "farkli", same),
        "kusurlu": _cevap("kusurlu", "saglam", faulty),
        "supheli": _cevap("supheli", "normal", shady),
    }


def fake_jev(calls: list | None = None, fail_status: int | None = None) -> httpx.MockTransport:
    """Başlığa bakarak karar veren sahte Jev sunucusu."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        if calls is not None:
            calls.append({"url": str(request.url), "auth": request.headers.get("authorization"), "body": body})
        if fail_status:
            return httpx.Response(fail_status, json={"error": {"message": "olmadı"}})
        state = body["state"]
        text = state.lower() if isinstance(state, str) else (state["ilan"]["baslik"] + " " + str(state["ilan"].get("aciklama", ""))).lower()
        title, desc = text, text
        if "kutusu" in title:
            answers = _answers("aksesuar_parca", same=0.3)
        elif "mor renk" in title or "mini" in title:  # kuralların göremediği model farkını taklit eder
            answers = _answers(same=0.05)
        elif "kilitli" in title:
            answers = _answers(faulty=0.97)
        elif "kapora" in desc:
            answers = _answers(shady=0.9)
        else:
            answers = _answers()
        return httpx.Response(200, json={"model": "jev", "answers": answers, "usage": {}})

    return httpx.MockTransport(handler)


def test_systemone_url_variants():
    assert systemone_url("https://gw.ornek.com/v1") == "https://gw.ornek.com/v1/systemone"
    assert systemone_url("http://127.0.0.1:8000/") == "http://127.0.0.1:8000/v1/systemone"
    assert systemone_url("http://x/v1/systemone") == "http://x/v1/systemone"
    with pytest.raises(DecisionError):
        systemone_url(" ")


def test_engine_protocol_retry_and_errors():
    calls: list = []
    engine = DecisionEngine("https://gw.example/v1", "sk-test", "jev", transport=fake_jev(calls))
    answers = engine.decide({"ilan": {"baslik": "iPhone 13 kutusu"}}, LISTING_QUESTIONS)
    assert answers["ilan_turu"]["choice"] == "aksesuar_parca"
    assert calls[0]["url"] == "https://gw.example/v1/systemone"
    assert calls[0]["auth"] == "Bearer sk-test" and calls[0]["body"]["model"] == "jev"
    assert set(calls[0]["body"]["questions"]) == {"ilan_turu", "ayni_urun", "kusurlu", "supheli"}

    # Laya (yerel) anahtarsız: Authorization başlığı gönderilmez
    local: list = []
    DecisionEngine("http://127.0.0.1:8000", "", "multilingual", transport=fake_jev(local)).decide(
        {"ilan": {"baslik": "PS5"}}, LISTING_QUESTIONS)
    assert local[0]["auth"] is None and local[0]["url"].endswith(":8000/v1/systemone")

    attempts = {"n": 0}

    def busy_then_ok(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(503, headers={"Retry-After": "0"}, json={"detail": "server busy"})
        return httpx.Response(200, json={"answers": _answers()})

    assert DecisionEngine("http://l", transport=httpx.MockTransport(busy_then_ok)).decide({}, {})["ayni_urun"]
    assert attempts["n"] == 2

    with pytest.raises(DecisionError, match="anahtar"):
        DecisionEngine("http://l", "yanlis", transport=fake_jev(fail_status=401)).decide({}, {})
    with pytest.raises(DecisionError, match="HTTP 422"):
        DecisionEngine("http://l", transport=fake_jev(fail_status=422)).decide({}, {})


def _deal(score=80.0) -> Deal:
    return Deal(listing_id=1, score=score, is_deal=True, reasons=["x"])


def test_apply_decision_rejects_and_keeps():
    accessory = apply_decision(_deal(), _answers("aksesuar_parca"))
    assert not accessory.is_deal and accessory.score <= 30 and accessory.fast["elendi"]
    assert any("aksesuar" in f.text.lower() for f in accessory.risk_flags)

    other_model = apply_decision(_deal(), _answers(same=0.1))
    assert not other_model.is_deal and any("farklı model" in f.text for f in other_model.risk_flags)

    assert not apply_decision(_deal(), _answers(faulty=0.9)).is_deal
    assert not apply_decision(_deal(), _answers(shady=0.8)).is_deal

    good = apply_decision(_deal(), _answers(same=0.55))  # belirsiz "aynı ürün" elemez
    assert good.is_deal and good.score == 80.0 and not good.fast["elendi"]
    clean = apply_decision(_deal(), _answers())
    assert clean.is_deal and any("Hızlı kontrol" in r for r in clean.reasons)


ROWS = [
    (2001, "iPhone 13 128 GB Mavi Temiz", "31.000 TL"),
    (2002, "iPhone 13 128GB Kutulu Faturalı", "32.500 TL"),
    (2003, "iPhone 13 128 GB Gece Yarısı", "30.500 TL"),
    (2004, "iPhone 13 128 GB pil %90", "33.000 TL"),
    (2005, "iphone 13 128gb beyaz hatasız", "31.500 TL"),
    (2006, "iPhone 13 128 GB Yeşil", "31.900 TL"),
    (2007, "iPhone 13 128 GB Kırmızı", "32.000 TL"),
    (2008, "iPhone 13 128 GB kutusu", "22.500 TL"),
    (2009, "iPhone 13 128 GB Mor Renk", "23.000 TL"),
    (2010, "iPhone 13 128 GB acil", "24.500 TL"),
]
DETAIL = """<!doctype html><meta charset="utf-8"><h1>{title}</h1>
<div id="classifiedDescription">Temiz, kutulu faturalı. iCloud kilidi yok.</div>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    for i, title, _ in ROWS:
        d = root / "ilan" / f"urun-{i}" / "detay"
        d.mkdir(parents=True)
        (d / "index.html").write_text(DETAIL.format(title=title), encoding="utf-8")
    (root / "arama.html").write_text(_search_html(ROWS), encoding="utf-8")
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    requested: list[str] = []
    orig = _Quiet.do_GET

    def tracking(self):  # hangi sayfaların açıldığını kaydet
        requested.append(self.path)
        return orig(self)

    _Quiet.do_GET = tracking  # type: ignore[method-assign]
    yield f"http://127.0.0.1:{server.server_address[1]}", requested
    _Quiet.do_GET = orig  # type: ignore[method-assign]
    server.shutdown()


def _settings() -> Settings:
    settings = Settings()
    settings.browser.headless = True
    settings.browser.min_delay_ms = 0
    settings.browser.max_delay_ms = 10
    settings.market.max_pages = 1
    settings.market.fetch_details = 2
    return settings


def test_scan_rejects_accessory_and_other_model_before_opening_details(site, tmp_path):
    base, requested = site
    settings = _settings()
    db = Database(tmp_path / "t.db")
    watch = db.save_watch(Watch(name="iPhone 13 128", platform="sahibinden", search_url=f"{base}/arama.html",
                                min_profit=2000, min_margin_pct=8))
    calls: list = []
    engine = DecisionEngine("https://gw/v1", "k", "jev", name="jev", transport=fake_jev(calls))
    budget = RequestBudget(db, "sahibinden", 60)
    pool = BrowserPool(tmp_path / "tarayici", lambda: settings)
    try:
        scanner = MarketScanner(db, settings, None, ScriptedInteraction(), tmp_path, decision=engine, budget=budget)
        summary = pool.worker("sahibinden-tarama").run(lambda s: scanner.scan_watch(s, watch))
        assert summary.fast_rejected >= 2 and summary.fast_checked >= 3
        by_id = {listing.external_id: deal for deal, listing in db.list_deals(only_deals=False)}
        assert not by_id["2008"].is_deal and by_id["2008"].fast["ilan_turu"] == "aksesuar_parca"
        assert not by_id["2009"].is_deal and by_id["2009"].fast["ayni_urun"] == 0.05
        assert by_id["2010"].is_deal and by_id["2010"].fast["motor"] == "jev"
        # Elenen ilanların detay sayfası hiç açılmadı; gerçek aday açıldı
        assert not any("urun-2008" in r or "urun-2009" in r for r in requested)
        assert any("urun-2010" in r for r in requested)
        assert budget.used() == 1 + sum("/detay" in r for r in requested)

        # Aynı ilan tekrar değerlendirilirse karar motoruna yeniden sorulmaz (önbellek)
        before = len(calls)
        watch = db.get_watch(watch.id)
        watch.last_run_at = None  # ilk tarama gibi hepsini yeniden değerlendir
        scanner2 = MarketScanner(db, settings, None, ScriptedInteraction(), tmp_path, decision=engine, budget=budget)
        pool.worker("sahibinden-tarama").run(lambda s: scanner2.scan_watch(s, watch))
        assert len(calls) == before
    finally:
        pool.shutdown()
        db.close()


def test_engine_failure_falls_back_to_rules(site, tmp_path):
    base, _ = site
    settings = _settings()
    db = Database(tmp_path / "t.db")
    watch = db.save_watch(Watch(name="iPhone 13", platform="sahibinden", search_url=f"{base}/arama.html",
                                min_profit=2000, min_margin_pct=8))
    engine = DecisionEngine("https://gw/v1", "k", "jev", transport=fake_jev(fail_status=500))
    ui = ScriptedInteraction()
    pool = BrowserPool(tmp_path / "tarayici", lambda: settings)
    try:
        scanner = MarketScanner(db, settings, None, ui, tmp_path, decision=engine)
        summary = pool.worker("sahibinden-tarama").run(lambda s: scanner.scan_watch(s, watch))
        assert summary.deals >= 1 and summary.fast_rejected == 0
        assert any("kural tabanlı" in m for m in ui.logs)
    finally:
        pool.shutdown()
        db.close()


class _Paged(http.server.BaseHTTPRequestHandler):
    pages: dict[int, list] = {}

    def do_GET(self):  # noqa: N802
        offset = int(self.path.split("pagingOffset=")[1].split("&")[0]) if "pagingOffset=" in self.path else 0
        rows = self.pages.get(offset // 20 + 1, [])
        html = _search_html(rows) + ('<a href="#">Sonraki</a>' if self.pages.get(offset // 20 + 2) else "")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def log_message(self, *args):
        pass


def test_quick_scan_reads_first_page_until_known_listing(tmp_path):
    _Paged.pages = {
        1: [(3000 + i, f"PS5 Diskli {i}", "18.000 TL") for i in range(1, 6)],
        2: [(3100 + i, f"PS5 Diskli Kol {i}", "18.500 TL") for i in range(1, 6)],
    }
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _Paged)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    settings = _settings()
    settings.market.max_pages = 2
    db = Database(tmp_path / "t.db")
    watch = db.save_watch(Watch(name="PS5", platform="sahibinden", search_url=f"{base}/arama"))
    pool = BrowserPool(tmp_path / "tarayici", lambda: settings)
    try:
        scanner = MarketScanner(db, settings, None, ScriptedInteraction(), tmp_path)
        first = pool.worker("sahibinden-tarama").run(lambda s: scanner.scan_watch(s, watch))
        assert first.deep and first.pages == 2 and first.total == 10

        # Hızlı tarama: ilk sayfada bilinen ilan var → ikinci sayfa açılmaz
        watch = db.get_watch(watch.id)
        assert watch.last_deep_scan_at
        second = pool.worker("sahibinden-tarama").run(lambda s: scanner.scan_watch(s, watch))
        assert not second.deep and second.pages == 1

        # İlk sayfanın tamamı yeni ilanlarsa (çok ilan düştüyse) sonraki sayfaya da bakılır
        _Paged.pages[1] = [(3200 + i, f"PS5 Dijital {i}", "16.000 TL") for i in range(1, 6)]
        watch = db.get_watch(watch.id)
        third = pool.worker("sahibinden-tarama").run(lambda s: scanner.scan_watch(s, watch))
        assert not third.deep and third.pages == 2 and third.new == 5
    finally:
        pool.shutdown()
        server.shutdown()
        db.close()


def test_request_budget_limits_scans(tmp_path):
    db = Database(tmp_path / "t.db")
    budget = RequestBudget(db, "letgo", 3)
    now = time.time()
    assert budget.take(now=now) and budget.take(2, now=now + 1)
    assert not budget.take(now=now + 2) and budget.left(now=now + 2) == 0
    assert budget.minutes_until(now=now + 2) == 60
    assert budget.left(now=now + 3700) == 3  # bir saat geçince haklar geri gelir
    assert RequestBudget(db, "sahibinden", 0).take(50)  # 0 = sınırsız
    db.close()

    app = AutoSell(tmp_path / "veri")
    app.settings_store.update({"market": {"hourly_request_budget": 2}})
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        watch = app.db.save_watch(Watch(name="PS5", platform="letgo", query="ps5"))
        assert watch.id in app.scheduler.due_watches()
        RequestBudget(app.db, "letgo", 2).take(2)
        assert watch.id not in app.scheduler.due_watches()  # bütçe dolu: zamanlayıcı bekler
        r = client.post(f"/api/watches/{watch.id}/scan")
        assert r.status_code == 400 and "istek sınırı" in r.json()["detail"]
        status = client.get("/api/status").json()
        assert status["budgets"]["letgo"]["used"] == 2 and status["budgets"]["letgo"]["limit"] == 2
    finally:
        app.shutdown()


def test_scheduler_jitter_and_decision_status(tmp_path):
    app = AutoSell(tmp_path / "veri")
    app.settings_store.update({"market": {"interval_jitter_pct": 20, "min_interval_min": 2}})
    try:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        watch = app.db.save_watch(Watch(name="x", platform="sahibinden", query="ps5", interval_min=10,
                                        last_run_at=(now - timedelta(minutes=7)).isoformat()))
        assert watch.id not in app.scheduler.due_watches(now)  # 10 dk ±%20 dolmadı
        assert watch.id in app.scheduler.due_watches(now + timedelta(minutes=5))  # 12 dk geçti

        # Varsayılan: kapalı. Adres girilmedikçe hiçbir motor hazır değil.
        assert not app.decision_ready()
        app.settings_store.update({"decision": {"engine": "laya"}})
        assert not app.decision_ready()
        # Jev: adres ve anahtar gerekir. Laya: adres yeter (anahtarsız çalışabilir).
        app.settings_store.update({"decision": {"engine": "jev", "base_url": "https://openrouter.ai/api/v1"}})
        assert not app.decision_ready()
        app.settings_store.update({"decision": {"api_key": "sk-or-deneme"}})
        assert app.decision_ready()
        app.settings_store.update({"decision": {"engine": "laya", "base_url": "http://127.0.0.1:8000",
                                                "api_key": ""}})
        assert app.decision_ready()
        assert app.settings.decision_endpoint() == ("http://127.0.0.1:8000", "", "multilingual")
        app.settings_store.update({"decision": {"engine": "kapali"}})
        assert not app.decision_ready() and app.decision_engine() is None
    finally:
        app.shutdown()


def test_decision_test_endpoint(tmp_path):
    app = AutoSell(tmp_path / "veri")
    app.decision_override = DecisionEngine("https://gw/v1", "k", "jev", name="jev", transport=fake_jev())
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        r = client.post("/api/settings/test-decision").json()
        assert r["ok"] and r["reliable"] and r["correct"] == r["total"] == 13

        # Her şeye "alım/takas" diyen (eğitilmemiş) bir motor güvenilmez olarak raporlanır
        def always_trade(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"answers": _answers("alim_takas", same=0.9, faulty=0.8, shady=0.8)})

        app.decision_override = DecisionEngine("http://127.0.0.1:8000", transport=httpx.MockTransport(always_trade))
        r = client.post("/api/settings/test-decision").json()
        assert not r["reliable"] and r["correct"] < r["total"] and "güvenilir değil" in r["verdict"]
        app.decision_override = None
        app.settings_store.update({"decision": {"engine": "kapali"}})
        r = client.post("/api/settings/test-decision")
        assert r.status_code == 400 and "kapalı" in r.json()["detail"]
    finally:
        app.shutdown()


def test_users_can_bring_their_own_decision_endpoint(tmp_path, monkeypatch):
    """Kullanıcı kendi Jev/Laya sağlayıcısını (adres, anahtar, model) girebilir; yapay zekâ anahtarı
    yalnızca aynı sunucuya gönderilir."""
    for env in ("OPENAI_API_KEY", "AUTOSELL_DECISION_API_KEY", "LAYA_API_KEY"):
        monkeypatch.delenv(env, raising=False)
    s = Settings()
    assert s.decision.engine == "kapali" and s.decision_endpoint() is None  # hazır sağlayıcı yok
    s.decision.engine = "jev"
    assert s.decision_endpoint() is None  # adres girilmedikçe motor kullanılmaz
    s.ai.openai_base_url, s.ai.openai_api_key = "https://gw.ornek.com/v1", "sk-yapay-zeka"
    s.decision.base_url = "https://gw.ornek.com/v1"  # yapay zekâyla aynı sunucu: aynı anahtar
    assert s.decision_endpoint() == ("https://gw.ornek.com/v1", "sk-yapay-zeka", "jev")

    s.decision.base_url, s.decision.model = "https://openrouter.ai/api/v1", "typesafe/jev-1.13"
    assert s.decision_endpoint()[1] == ""  # yapay zekâ anahtarı OpenRouter'a gönderilmez
    s.decision.api_key = "sk-or-kendi"
    assert s.decision_endpoint() == ("https://openrouter.ai/api/v1", "sk-or-kendi", "typesafe/jev-1.13")

    s.decision.api_key = ""
    s.ai.openai_base_url = "https://openrouter.ai/api/v1"  # yapay zekâ da OpenRouter'daysa aynı anahtar
    assert s.decision_endpoint()[1] == "sk-yapay-zeka"

    monkeypatch.setenv("AUTOSELL_DECISION_API_KEY", "sk-ortam")
    assert s.decision_endpoint()[1] == "sk-ortam"
    s.decision.engine, s.decision.base_url, s.decision.model = "laya", "https://laya.benim-sunucum.com", ""
    assert s.decision_endpoint() == ("https://laya.benim-sunucum.com", "sk-ortam", "multilingual")
    monkeypatch.delenv("AUTOSELL_DECISION_API_KEY")
    monkeypatch.setenv("LAYA_API_KEY", "laya-anahtar")
    assert s.decision_endpoint()[1] == "laya-anahtar"

    # Kendi sunucusuna giden istek: doğru adres, anahtar ve model
    calls: list = []
    base, key, model = s.decision_endpoint()
    DecisionEngine(base, key, model, transport=fake_jev(calls)).decide({"ilan": {"baslik": "PS5"}}, LISTING_QUESTIONS)
    assert calls[0]["url"] == "https://laya.benim-sunucum.com/v1/systemone"
    assert calls[0]["auth"] == "Bearer laya-anahtar" and calls[0]["body"]["model"] == "multilingual"


def test_settings_reject_invalid_decision_url(tmp_path):
    app = AutoSell(tmp_path / "veri")
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        r = client.put("/api/settings", json={"decision": {"engine": "laya", "base_url": "https://"}})
        assert r.status_code == 400 and "geçersiz" in r.json()["detail"]
        r = client.put("/api/settings", json={"decision": {"engine": "jev", "base_url": "https://openrouter.ai/api/v1",
                                                            "api_key": "sk-or-deneme", "model": "typesafe/jev-1.13"}})
        assert r.status_code == 200
        data = r.json()
        assert data["decision"]["base_url"] == "https://openrouter.ai/api/v1"
        assert data["decision"]["api_key"].startswith("••••") and "sk-or-deneme" not in r.text  # anahtar maskeli
        assert app.settings.decision.api_key == "sk-or-deneme"
    finally:
        app.shutdown()
