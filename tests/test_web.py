"""Web API testleri (demo yapay zekâ ile; tarayıcı açılmaz)."""

import io
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from autosell.demo import DemoProvider, seed_demo
from autosell.models import Watch
from autosell.service import AutoSell
from autosell.web import create_app


def _jpeg(color=(10, 120, 200)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), color).save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture
def service(tmp_path):
    app = AutoSell(tmp_path / "veri")
    app.provider_override = DemoProvider()
    yield app
    app.shutdown()


@pytest.fixture
def client(service):
    return TestClient(create_app(service), headers={"X-AutoSell": "1"})


def test_csrf_header_and_host_checks(service):
    raw = TestClient(create_app(service))
    assert raw.get("/api/drafts").status_code == 200
    assert raw.post("/api/drafts", data={"notes": "x"}).status_code == 403  # özel başlık yok
    evil = TestClient(create_app(service), base_url="http://kotu-site.example", headers={"X-AutoSell": "1"})
    assert evil.get("/api/drafts").status_code == 403  # şifresiz panel yalnız yerelden


def _wait_job(client, job_id, timeout=10):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] not in ("queued", "running", "waiting"):
            return job
        time.sleep(0.1)
    raise AssertionError("iş bitmedi")


def test_create_generate_edit_draft(client, service):
    r = client.post(
        "/api/drafts",
        data={"notes": "iPhone 13 128GB mavi, pil %89", "price": "32.500", "platforms": "sahibinden,letgo"},
        files=[("photos", ("a.jpg", _jpeg(), "image/jpeg")), ("photos", ("b.jpg", _jpeg((200, 0, 0)), "image/jpeg"))],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    draft_id = body["draft"]["id"]
    assert body["draft"]["price"] == 32500 and len(body["draft"]["photo_urls"]) == 2
    job = _wait_job(client, body["job"]["id"])
    assert job["status"] == "done", job

    draft = client.get(f"/api/drafts/{draft_id}").json()
    sah = draft["listings"]["sahibinden"]
    assert sah["title"] and len(sah["title"]) <= draft["rules"]["sahibinden"]["title_max"]
    assert sah["title_candidates"][0]["score"] >= sah["title_candidates"][-1]["score"]

    photo = client.get(draft["photo_urls"][0])
    assert photo.status_code == 200 and photo.headers["content-type"] == "image/jpeg"
    assert client.get(f"/api/drafts/{draft_id}/photos/..%2F..%2Fayarlar.json").status_code == 404

    new_order = list(reversed(draft["photos"]))
    patch = {"price": 31000, "photos": new_order,
             "listings": {"letgo": {"title": "Elle düzeltilmiş başlık", "attributes": [{"name": "Renk", "value": "Mavi"}]}}}
    updated = client.put(f"/api/drafts/{draft_id}", json=patch).json()
    assert updated["price"] == 31000 and updated["photos"] == new_order
    assert updated["listings"]["letgo"]["title"] == "Elle düzeltilmiş başlık"
    assert updated["listings"]["letgo"]["description"]  # diğer alanlar korunur

    deleted = client.delete(f"/api/drafts/{draft_id}/photos/{new_order[0]}").json()
    assert deleted["photos"] == new_order[1:]
    assert client.get("/api/drafts").json()[0]["id"] == draft_id
    assert client.delete(f"/api/drafts/{draft_id}").json()["ok"]
    assert client.get(f"/api/drafts/{draft_id}").status_code == 404


def test_draft_validation(client):
    assert client.post("/api/drafts", data={"notes": ""}).status_code == 400
    assert client.post("/api/drafts", data={"notes": "x", "price": "abc"}).status_code == 400


def test_title_score_endpoint(client):
    r = client.post("/api/title-score", json={"platform": "sahibinden", "title": "Apple iPhone 13 128 GB Mavi Kutulu"})
    data = r.json()
    assert data["max"] == 50 and data["length"] == 34 and 0 < data["score"] <= 100


def test_settings_masking_and_password(client, service):
    s = client.put("/api/settings", json={"ai": {"openai_api_key": "sk-abcdefghijkl"}}).json()
    assert s["ai"]["openai_api_key"].startswith("••••") and s["_secrets"]["ai.openai_api_key"]["set"]
    client.put("/api/settings", json={"ai": {"openai_api_key": s["ai"]["openai_api_key"]}})
    assert service.settings.ai.openai_api_key == "sk-abcdefghijkl"

    client.put("/api/settings", json={"web": {"password": "gizli123"}})
    assert client.get("/api/drafts").status_code == 401
    assert client.get("/api/auth").json() == {"required": True, "ok": False}
    assert client.post("/api/login", json={"password": "yanlis"}).status_code == 401
    assert client.post("/api/login", json={"password": "gizli123"}).status_code == 200
    assert client.get("/api/drafts").status_code == 200
    assert client.get("/api/auth").json()["ok"] is True


def test_watches_and_deals(client, service):
    seed_demo(service)
    watches = client.get("/api/watches").json()
    assert {w["name"] for w in watches} == {"iPhone 13 128 GB", "PS5 fırsatları"}
    assert client.post("/api/watches", json={"name": "boş"}).status_code == 400
    created = client.post("/api/watches", json={"name": "Clio", "platform": "sahibinden", "query": "clio 1.5 dci",
                                                "interval_min": 1}).json()
    assert created["interval_min"] >= service.settings.market.min_interval_min
    edited = client.put(f"/api/watches/{created['id']}", json={"active": False}).json()
    assert edited["active"] is False and edited["query"] == "clio 1.5 dci"

    deals = client.get("/api/deals").json()
    assert deals and all(d["deal"]["is_deal"] for d in deals)
    assert deals == sorted(deals, key=lambda d: -d["deal"]["score"])
    best = deals[0]
    assert best["listing"]["title"] == "iPhone 13 128 GB acil satılık"
    detail = client.get(f"/api/deals/{best['deal']['id']}").json()
    assert [h["price"] for h in detail["price_history"]] == [25900, 24900]
    client.put(f"/api/deals/{best['deal']['id']}", json={"status": "gizli"})
    assert best["deal"]["id"] not in [d["deal"]["id"] for d in client.get("/api/deals").json()]
    assert client.put(f"/api/deals/{best['deal']['id']}", json={"status": "kötü"}).status_code == 422
    all_candidates = client.get("/api/deals?all=1").json()
    assert len(all_candidates) > len(deals) - 1


def test_scheduler_due_logic(service):
    now = datetime.now(timezone.utc)
    fresh = service.db.save_watch(Watch(name="yeni", query="a", interval_min=15,
                                        last_run_at=(now - timedelta(minutes=5)).isoformat()))
    stale = service.db.save_watch(Watch(name="eski", query="b", interval_min=15,
                                        last_run_at=(now - timedelta(minutes=20)).isoformat()))
    never = service.db.save_watch(Watch(name="hiç", query="c"))
    service.db.save_watch(Watch(name="pasif", query="d", active=False))
    assert set(service.scheduler.due_watches(now)) == {stale.id, never.id}
    assert fresh.id not in service.scheduler.due_watches(now)
