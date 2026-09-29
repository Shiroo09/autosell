"""İlan verme durum makinesinin dalları: kategori → form (doğrulama hatası ve düzeltme) →
doping (ücretsiz geçiş) → onay → başarı. Sayfalar testte üretilir ve yerelde sunulur."""

from __future__ import annotations

import functools
import http.server
import json
import socketserver
import threading
from pathlib import Path

import pytest

from autosell.automation.browser import BrowserPool
from autosell.automation.interaction import Interaction
from autosell.automation.platforms.base import PlatformAdapter, PublishCancelled
from autosell.config import Settings
from autosell.models import Attribute, Draft, PlatformListing, ProductInfo

from .conftest import FakeProvider

PAGES = {
    "start.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<header><a href="#">Çıkış</a></header>
<h2>Kategori Seçimi</h2>
<ul id="l1"><li onclick="lvl2()">Elektronik</li><li>Ev &amp; Bahçe</li><li>Giyim</li></ul>
<ul id="l2"></ul><p id="msg"></p>
<a href="yardim.html">Kategori seçimi hakkında yardım</a>
<button id="devam" disabled onclick="location.href='form.html'">Devam</button>
<script>
function lvl2(){ setTimeout(()=>{ document.getElementById('l2').innerHTML =
  '<li onclick="leaf()">Telefon</li><li>Bilgisayar</li>'; }, 250); }
function leaf(){ sessionStorage.setItem('cat','Elektronik > Telefon');
  document.getElementById('msg').innerText='Kategori seçimi tamamlandı.';
  document.getElementById('devam').disabled=false; }
</script></body></html>""",
    "form.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<header><a href="#">Çıkış</a></header>
<div class="row"><div>İlan Başlığı *</div><input id="t" maxlength="40"><span class="error" id="e-t"></span></div>
<div class="row"><label for="d">Açıklama *</label><textarea id="d"></textarea></div>
<div class="row"><div>Fiyat *</div><input id="p"></div>
<div class="row"><div>Renk</div><select id="r"><option value="">Seçiniz</option><option>Mavi</option><option>Siyah</option></select></div>
<div class="row"><div>Dahili Hafıza *</div><select id="h"><option value="">Seçiniz</option><option>64 GB</option><option>128 GB</option></select><span class="error" id="e-h"></span></div>
<button onclick="go()">Devam</button>
<script>
function go(){
  const h = document.getElementById('h').value;
  document.getElementById('e-h').innerText = h ? '' : 'Bu alan zorunludur.';
  if(!h || !document.getElementById('t').value) return;
  sessionStorage.setItem('data', JSON.stringify({title: document.getElementById('t').value,
    description: document.getElementById('d').value, price: document.getElementById('p').value,
    renk: document.getElementById('r').value, hafiza: h, cat: sessionStorage.getItem('cat')}));
  location.href = 'promo.html';
}
</script></body></html>""",
    "promo.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1>İlanınızı öne çıkarın: Doping</h1>
<button onclick="location.href='pay.html'">Doping Satın Al 99 TL</button>
<a href="confirm.html">Doping istemiyorum</a></body></html>""",
    "pay.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<script>sessionStorage.setItem('paid','1')</script>
<h1>Ödeme Bilgileri</h1><label>Kart Numarası <input autocomplete="cc-number"></label>
<button>Ödemeyi Tamamla</button></body></html>""",
    "confirm.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1>İlan Onayı</h1>
<label><input type="checkbox" id="ok"> Girdiğim bilgilerin doğruluğunu onaylıyorum.</label>
<button onclick="if(document.getElementById('ok').checked){location.href='done.html'}">İlanı Yayınla</button>
</body></html>""",
    "done.html": """<!doctype html><html><head><meta charset="utf-8"></head><body>
<h1>Tebrikler! İlanınız başarıyla oluşturuldu.</h1><p>İlan No: 555666777</p>
<pre id="data"></pre><pre id="paid"></pre>
<script>document.getElementById('data').innerText = sessionStorage.getItem('data');
document.getElementById('paid').innerText = sessionStorage.getItem('paid') || '0';</script>
</body></html>""",
}


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    for name, html in PAGES.items():
        (root / name).write_text(html, encoding="utf-8")
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


class ScriptedInteraction(Interaction):
    def __init__(self, answer: bool = True, on_human=None):
        self.answer = answer
        self.on_human = on_human
        self.logs: list[str] = []
        self.human: list[str] = []
        self.confirms: list[str] = []

    def log(self, message: str, level: str = "info") -> None:
        self.logs.append(message)

    def wait_for_human(self, reason, done, page, timeout_s):
        self.human.append(reason)
        if self.on_human:
            self.on_human(page)
        super().wait_for_human(reason, done, page, min(timeout_s, 10))

    def confirm(self, question, page, timeout_s, done=None):
        self.confirms.append(question)
        return self.answer


class _Adapter(PlatformAdapter):
    name = "sahibinden"


def _settings(site: str, auto: bool) -> Settings:
    s = Settings()
    s.browser.headless = True
    s.browser.slow_mo_ms = 0
    s.browser.min_delay_ms = 0
    s.browser.max_delay_ms = 10
    s.browser.human_timeout_s = 10
    s.sahibinden.post_url = f"{site}/start.html"
    s.sahibinden.auto_publish = auto
    return s


def _draft() -> Draft:
    return Draft(
        price=32500,
        platforms=["sahibinden"],
        product=ProductInfo(name="iPhone 13", brand="Apple", model="iPhone 13", condition="Çok İyi"),
        listings={"sahibinden": PlatformListing(
            category_path=["Elektronik", "Telefon"],
            title="Apple iPhone 13 128 GB Mavi Kutulu",
            description="Tertemiz iPhone 13.\n• 128 GB\n• Pil %89",
            attributes=[Attribute(name="Renk", value="Mavi")],
        )},
    )


def _chooser_answers(system, prompt, schema):
    props = schema["properties"]
    if "secim" in props:
        return {"secim": props["secim"]["enum"][0], "gerekce": "test"}
    # Form alanı seçimi: seçenekli alanlarda "128 GB" varsa onu seç
    return {k: ("128 GB" if "128 GB" in v.get("enum", []) else "") for k, v in props.items()}


def _run(settings, tmp_path, fn):
    pool = BrowserPool(tmp_path / "tarayici", lambda: settings)
    try:
        return pool.worker("sahibinden").run(fn)
    finally:
        pool.shutdown()


def test_full_flow_with_ai_field_choice(site, tmp_path):
    settings = _settings(site, auto=True)
    ui = ScriptedInteraction()
    provider = FakeProvider(_chooser_answers)
    adapter = _Adapter(settings, provider, ui, tmp_path)

    def flow(session):
        result = adapter.publish(session, _draft(), [])
        data = session.context.pages[-1].inner_text("#data")
        paid = session.context.pages[-1].inner_text("#paid")
        return result, json.loads(data), paid

    result, data, paid = _run(settings, tmp_path, flow)
    assert result.status == "yayinda" and result.listing_no == "555666777"
    assert data["title"] == "Apple iPhone 13 128 GB Mavi Kutulu"
    assert data["price"] == "32500" and data["renk"] == "Mavi" and data["hafiza"] == "128 GB"
    assert data["cat"] == "Elektronik > Telefon"
    assert "Tertemiz iPhone 13." in data["description"]
    assert paid == "0", "ödeme sayfası asla açılmamalı"
    assert any("öne çıkarma" in m for m in ui.logs)
    assert not ui.human


def test_user_declines_final_publish(site, tmp_path):
    settings = _settings(site, auto=False)
    ui = ScriptedInteraction(answer=False)
    adapter = _Adapter(settings, FakeProvider(_chooser_answers), ui, tmp_path)
    with pytest.raises(PublishCancelled):
        _run(settings, tmp_path, lambda session: adapter.publish(session, _draft(), []))
    assert ui.confirms, "son adımda onay istenmeli"


def test_without_ai_missing_field_is_handed_to_user(site, tmp_path):
    settings = _settings(site, auto=True)

    def human_fixes(page):
        if "form.html" in page.url:
            page.select_option("#h", label="128 GB")
            page.click("text=Devam")

    ui = ScriptedInteraction(on_human=human_fixes)
    adapter = _Adapter(settings, None, ui, tmp_path)
    result = _run(settings, tmp_path, lambda session: adapter.publish(session, _draft(), []))
    assert result.status == "yayinda"
    assert ui.human and "Dahili Hafıza" in ui.human[0]
