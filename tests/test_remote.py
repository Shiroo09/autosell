"""Uzaktan tarayıcı kontrolü: giriş işi kullanıcıyı beklerken panelden ekran izlenip
dokunma/yazma komutlarıyla giriş yapılabilmeli."""

from __future__ import annotations

import functools
import http.server
import socketserver
import threading
import time

import pytest
from fastapi.testclient import TestClient

from autosell.service import AutoSell
from autosell.web import create_app

LOGIN = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0} #ad{position:absolute;left:100px;top:100px;width:400px;height:60px;font-size:24px}
#btn{position:absolute;left:100px;top:300px;width:400px;height:80px}</style></head><body>
<header><a href="#">Giriş Yap</a></header>
<input id="ad" placeholder="E-posta"><input type="password" style="position:absolute;left:100px;top:200px">
<button id="btn" onclick="if(document.getElementById('ad').value==='deniz'){location.href='home.html'}">Giriş Yap</button>
</body></html>"""
HOME = """<!doctype html><html><head><meta charset="utf-8"></head><body>
<header><a href="#">Bana Özel</a> <a href="#">Çıkış</a></header><h1>Hoş geldin</h1></body></html>"""


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def site(tmp_path):
    root = tmp_path / "site"
    root.mkdir()
    (root / "login.html").write_text(LOGIN, encoding="utf-8")
    (root / "home.html").write_text(HOME, encoding="utf-8")
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(root)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def _until(fn, timeout=20.0, step=0.2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        value = fn()
        if value:
            return value
        time.sleep(step)
    raise AssertionError("koşul gerçekleşmedi")


def test_remote_login_through_panel(site, tmp_path):
    app = AutoSell(tmp_path / "veri")
    app.settings_store.update({
        "browser": {"headless": True, "slow_mo_ms": 0, "min_delay_ms": 0, "max_delay_ms": 10, "human_timeout_s": 40},
        "sahibinden": {"login_url": f"{site}/login.html", "home_url": f"{site}/home.html"},
    })
    client = TestClient(create_app(app), headers={"X-AutoSell": "1"})
    try:
        assert client.post("/api/browser/sahibinden/input", json={"type": "key", "key": "Enter"}).status_code == 409
        job = client.post("/api/platforms/sahibinden/login").json()
        _until(lambda: client.get("/api/browser/sahibinden/state").json()["active"])
        shot = _until(lambda: (r := client.get("/api/browser/sahibinden/screen")).status_code == 200 and r)
        assert shot.headers["content-type"] == "image/jpeg" and len(shot.content) > 1000
        state = client.get("/api/browser/sahibinden/state").json()
        w, h = state["width"], state["height"]
        assert client.get(f"/api/jobs/{job['id']}").json()["prompt"]["type"] == "human"

        client.post("/api/browser/sahibinden/input", json={"type": "click", "x": 300 / w, "y": 130 / h})
        client.post("/api/browser/sahibinden/input", json={"type": "type", "text": "deniz"})
        client.post("/api/browser/sahibinden/input", json={"type": "click", "x": 300 / w, "y": 340 / h})
        assert client.post("/api/browser/sahibinden/input", json={"type": "key", "key": "F12"}).status_code == 400

        final = _until(lambda: (j := client.get(f"/api/jobs/{job['id']}").json())["status"] in ("done", "error") and j)
        assert final["status"] == "done", final
        assert client.get("/api/browser/sahibinden/state").json()["active"] is False
    finally:
        app.shutdown()
