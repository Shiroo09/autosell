"""Fırsat avcısı taraması uçtan uca: arama sayfası → kayıt → emsal → puan → detay → fırsat."""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading

import pytest

from autosell.automation.browser import BrowserPool
from autosell.config import Settings
from autosell.db import Database
from autosell.market.scanner import MarketScanner
from autosell.models import Watch

from .conftest import FakeProvider
from .test_flow import ScriptedInteraction

ROWS = [
    (1001, "iPhone 13 128 GB Mavi Temiz", "31.000 TL"),
    (1002, "iPhone 13 128GB Kutulu Faturalı", "32.500 TL"),
    (1003, "iPhone 13 128 GB Gece Yarısı", "30.500 TL"),
    (1004, "iPhone 13 128 GB pil %90", "33.000 TL"),
    (1005, "iphone 13 128gb beyaz hatasız", "31.500 TL"),
    (1006, "iPhone 13 128 GB Yeşil", "29.900 TL"),
    (1007, "iPhone 13 128 GB Kırmızı", "32.000 TL"),
    (1008, "iPhone 13 128 GB acil satılık", "25.500 TL"),
    (1009, "iPhone 13 128 GB kapora ile kargo", "14.000 TL"),
    (1010, "iPhone 13 Kılıf Şeffaf", "250 TL"),
]


def _search_html(rows) -> str:
    trs = "".join(
        f'<tr class="searchResultsItem" data-id="{i}"><td class="searchResultsTitleValue">'
        f'<a class="classifiedTitle" href="ilan/urun-{i}/detay/">{t}</a></td>'
        f'<td class="searchResultsPriceValue">{p}</td><td class="searchResultsDateValue">Bugün</td>'
        f'<td class="searchResultsLocationValue">İstanbul<br>Kadıköy</td></tr>'
        for i, t, p in rows
    )
    return f'<!doctype html><meta charset="utf-8"><table id="searchResultsTable"><tbody>{trs}</tbody></table>'


DETAIL = """<!doctype html><meta charset="utf-8"><h1>iPhone 13 128 GB acil satılık</h1>
<div class="classifiedInfo"><h3>25.500 TL</h3><ul class="classifiedInfoList">
<li><strong>Dahili Hafıza</strong><span>128 GB</span></li></ul></div>
<div id="classifiedDescription">Taşınma nedeniyle acil satılık. Kutusu faturası var, iCloud kilidi yok.</div>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def market_site(tmp_path):
    root = tmp_path / "site"
    (root / "ilan" / "urun-1008" / "detay").mkdir(parents=True)
    (root / "ilan" / "urun-1008" / "detay" / "index.html").write_text(DETAIL, encoding="utf-8")
    (root / "arama.html").write_text(_search_html(ROWS), encoding="utf-8")
    (root / "arama2.html").write_text(_search_html(ROWS[:7] + [(1008, ROWS[7][1], "24.000 TL")]), encoding="utf-8")
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _review(system, prompt, schema):
    return {
        "ayni_urun_emsal_orani": 0.9, "duzeltilmis_piyasa_degeri": 31500, "hizli_satis_fiyati": 30500,
        "tahmini_net_kar": 5000, "risk_seviyesi": "dusuk", "riskler": [], "firsat_mi": True,
        "pazarlik_teklifi": 24000, "yorum": "Kârlı görünüyor.", "kaynaklar": [],
    }


def test_scan_watch_finds_deal_and_tracks_price_drop(market_site, tmp_path):
    settings = Settings()
    settings.browser.headless = True
    settings.browser.min_delay_ms = 0
    settings.browser.max_delay_ms = 10
    settings.market.max_pages = 1
    settings.market.fetch_details = 1
    settings.market.ai_evaluations = 1
    db = Database(tmp_path / "t.db")
    watch = db.save_watch(Watch(name="iPhone 13", platform="sahibinden", search_url=f"{market_site}/arama.html",
                                min_profit=2000, min_margin_pct=8, exclude_words=["kılıf"]))
    provider = FakeProvider(_review)
    ui = ScriptedInteraction()
    pool = BrowserPool(tmp_path / "tarayici", lambda: settings)
    try:
        scanner = MarketScanner(db, settings, provider, ui, tmp_path)
        summary = pool.worker("sahibinden").run(lambda s: scanner.scan_watch(s, watch))
        assert summary.total == 9  # kılıf dışlandı
        assert summary.new == 9 and summary.deals >= 1 and summary.ai_reviews == 1

        deals = db.list_deals()
        best_deal, best_listing = deals[0]
        assert best_listing.external_id == "1008"
        assert best_deal.ai and best_deal.ai["pazarlik_teklifi"] == 24000
        assert "iCloud kilidi yok" in best_listing.details.get("description", "")
        scam = [d for d, listing in db.list_deals(only_deals=False) if listing.external_id == "1009"]
        assert scam and not scam[0].is_deal and any(f.level == "yuksek" for f in scam[0].risk_flags)

        # İkinci tarama: ilan 1008'in fiyatı düştü
        watch = db.get_watch(watch.id)
        watch.search_url = f"{market_site}/arama2.html"
        db.save_watch(watch)
        summary2 = pool.worker("sahibinden").run(lambda s: scanner.scan_watch(s, watch))
        assert summary2.new == 0 and summary2.price_changed == 1
        again = db.get_deal_by_listing(best_listing.id)
        assert any("Fiyatı düştü" in r for r in again.reasons)
        assert db.get_watch(watch.id).last_status.startswith("8 ilan")
    finally:
        pool.shutdown()
        db.close()
