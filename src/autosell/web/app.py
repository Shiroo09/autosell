"""Web paneli (FastAPI). Arayüz: static/ altındaki tek sayfalık uygulama."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import Body, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..ai import AIError, AINotConfigured
from ..ai.decision import DecisionError
from ..config import PLATFORM_NAMES, PLATFORMS
from ..listing import rules_for, score_title
from ..models import DealStatus
from ..safety import SCAN_SUFFIX, PublishBlocked, clear_cooldown
from ..service import AutoSell

log = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).parent / "static"
COOKIE = "autosell_oturum"
CSRF_HEADER = "x-autosell"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}
MAX_PHOTO_BYTES = 25 * 1024 * 1024


def _session_secret(app_service: AutoSell) -> bytes:
    path = app_service.paths.root / ".oturum-anahtari"
    if not path.exists():
        path.write_text(secrets.token_hex(32), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text(encoding="utf-8").strip().encode()


def _token(secret: bytes, password: str) -> str:
    return hmac.new(secret, password.encode(), hashlib.sha256).hexdigest()


def draft_summary(app_service: AutoSell, draft: Any) -> dict[str, Any]:
    return {
        "id": draft.id,
        "title": draft.display_title(),
        "price": draft.price,
        "currency": draft.currency,
        "platforms": draft.platforms,
        "cover": f"/api/drafts/{draft.id}/photos/{draft.photos[0]}" if draft.photos else None,
        "photo_count": len(draft.photos),
        "publications": {k: v.model_dump() for k, v in draft.publications.items()},
        "generated": draft.generated,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
    }


def draft_full(app_service: AutoSell, draft: Any) -> dict[str, Any]:
    data = draft.model_dump()
    data["photo_urls"] = [f"/api/drafts/{draft.id}/photos/{name}" for name in draft.photos]
    settings = app_service.settings
    data["rules"] = {
        p: {
            "title_max": rules_for(p, settings).title_max,
            "description_max": rules_for(p, settings).description_max,
            "use_emoji": rules_for(p, settings).use_emoji,
            "name": PLATFORM_NAMES[p],
        }
        for p in PLATFORMS
    }
    data["display_title"] = draft.display_title()
    return data


def deal_view(deal: Any, listing: Any) -> dict[str, Any]:
    return {"deal": deal.model_dump(), "listing": listing.model_dump()}


async def _read_photos(files: list[UploadFile] | None) -> list[tuple[str, bytes]]:
    out: list[tuple[str, bytes]] = []
    for f in files or []:
        if not f or not f.filename:
            continue
        data = await f.read()
        if len(data) > MAX_PHOTO_BYTES:
            raise HTTPException(413, f"{f.filename} çok büyük (en fazla 25 MB).")
        if data:
            out.append((f.filename, data))
    return out


def create_app(app_service: AutoSell | None = None) -> FastAPI:
    service = app_service or AutoSell(start_scheduler=True)
    secret = _session_secret(service)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        service.shutdown()  # sunucu kapanırken tarayıcıları ve işleri kapat

    api = FastAPI(title="AutoSell", version=__version__, docs_url="/api/docs", redoc_url=None, lifespan=lifespan)
    api.state.service = service

    @api.middleware("http")
    async def auth_guard(request: Request, call_next):  # type: ignore[no-untyped-def]
        path = request.url.path
        password = service.settings.panel_password()
        if path.startswith("/api/"):
            # Şifresiz panel yalnızca bu bilgisayardan açılabilir (DNS rebinding koruması)
            host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
            if not password and host not in LOCAL_HOSTS:
                return JSONResponse({"detail": "Panele ağdan erişmek için Ayarlar'dan şifre belirleyin."},
                                    status_code=403)
            # Değişiklik yapan istekler özel başlık taşımalı: başka sitelerden gelen
            # istekler (CSRF) bu başlığı CORS ön kontrolü olmadan gönderemez.
            if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(CSRF_HEADER) != "1":
                return JSONResponse({"detail": "Geçersiz istek kaynağı."}, status_code=403)
        if password and path.startswith("/api/") and path not in ("/api/auth", "/api/login"):
            token = request.cookies.get(COOKIE, "")
            if not hmac.compare_digest(token, _token(secret, password)):
                return JSONResponse({"detail": "Oturum açmanız gerekiyor."}, status_code=401)
        return await call_next(request)

    @api.exception_handler(KeyError)
    async def not_found(_request: Request, exc: KeyError) -> JSONResponse:
        return JSONResponse({"detail": str(exc).strip("'\"")}, status_code=404)

    @api.exception_handler(PublishBlocked)
    async def publish_blocked(_request: Request, exc: PublishBlocked) -> JSONResponse:
        # 409: kural gereği durduruldu; "duplicate"/"already_published" için arayüz "Yine de yayınla" sunar
        return JSONResponse({"detail": str(exc), "code": exc.code}, status_code=409)

    @api.exception_handler(ValueError)
    async def bad_value(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    # ------------------------------------------------------------ oturum

    @api.get("/api/auth")
    def auth_state(request: Request) -> dict[str, Any]:
        password = service.settings.panel_password()
        ok = not password or hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(secret, password))
        return {"required": bool(password), "ok": ok}

    @api.post("/api/login")
    def login(response: Response, password: str = Body(..., embed=True)) -> dict[str, Any]:
        expected = service.settings.panel_password()
        if not expected or not hmac.compare_digest(password, expected):
            raise HTTPException(401, "Şifre hatalı.")
        response.set_cookie(COOKIE, _token(secret, expected), httponly=True, samesite="lax", max_age=30 * 86400)
        return {"ok": True}

    @api.post("/api/logout")
    def logout(response: Response) -> dict[str, Any]:
        response.delete_cookie(COOKIE)
        return {"ok": True}

    # ------------------------------------------------------------ durum & ayarlar

    @api.get("/api/status")
    def status() -> dict[str, Any]:
        s = service.settings
        configured = True
        try:
            provider = service.provider()
            ai_desc = provider.describe() if provider else ""
        except AINotConfigured as exc:
            configured, ai_desc = False, str(exc)
        return {
            "version": __version__,
            "ai": {"provider": s.ai.provider, "configured": configured, "description": ai_desc},
            "stats": service.db.stats(),
            "browsers": service.pool.status(),
            "active_jobs": [j.to_dict(since=max(0, len(j.logs) - 3)) for j in service.jobs.list(active_only=True)],
            "platforms": {
                p: {"name": PLATFORM_NAMES[p], "enabled": s.platform(p).enabled,
                    "auto_publish": s.platform(p).auto_publish}
                for p in PLATFORMS
            },
            "seller_ready": bool(s.seller.city and s.seller.district),
            "cooldowns": {p: service.scan_cooldown(p) for p in PLATFORMS if service.scan_cooldown(p)},
            "budgets": service.budget_status(),
            "decision": {"engine": s.decision.engine, "ready": service.decision_ready()},
        }

    @api.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        return service.settings_store.public_dict()

    @api.put("/api/settings")
    def put_settings(patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        patch.pop("_secrets", None)
        try:
            service.settings_store.update(patch)
        except Exception as exc:  # doğrulama hatası
            raise HTTPException(400, f"Ayarlar kaydedilemedi: {exc}") from exc
        return service.settings_store.public_dict()

    @api.post("/api/settings/test-ai")
    def test_ai() -> dict[str, Any]:
        try:
            return service.test_ai()
        except AIError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/api/settings/test-decision")
    def test_decision() -> dict[str, Any]:
        try:
            return service.test_decision()
        except DecisionError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.get("/api/settings/models")
    def list_models() -> dict[str, Any]:
        try:
            provider = service.provider()
            assert provider is not None
            return {"provider": provider.name, "current": provider.model, "models": provider.list_models()}
        except AIError as exc:
            raise HTTPException(400, str(exc)) from exc

    @api.post("/api/settings/test-telegram")
    def test_telegram() -> dict[str, Any]:
        ok, detail = service.test_telegram()
        if not ok:
            raise HTTPException(400, detail or "Bildirim gönderilemedi.")
        return {"ok": True}

    # ------------------------------------------------------------ taslaklar

    @api.get("/api/drafts")
    def list_drafts() -> list[dict[str, Any]]:
        return [draft_summary(service, d) for d in service.db.list_drafts()]

    @api.post("/api/drafts")
    async def create_draft(
        notes: str = Form(""),
        price: str = Form(""),
        platforms: str = Form(""),
        generate: bool = Form(True),
        photos: list[UploadFile] | None = File(None),
    ) -> dict[str, Any]:
        files = await _read_photos(photos)
        if not files and not notes.strip():
            raise HTTPException(400, "En az bir fotoğraf ya da ürün notu ekleyin.")
        price_value = _parse_price_form(price)
        draft = service.create_draft(
            notes=notes, price=price_value, platforms=[p.strip() for p in platforms.split(",") if p.strip()],
            photos=files,
        )
        job = service.start_generate(draft.id) if generate else None
        return {"draft": draft_full(service, draft), "job": job.to_dict() if job else None}

    @api.get("/api/drafts/{draft_id}")
    def get_draft(draft_id: str) -> dict[str, Any]:
        return draft_full(service, service.draft_or_404(draft_id))

    @api.put("/api/drafts/{draft_id}")
    def update_draft(draft_id: str, patch: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return draft_full(service, service.update_draft(draft_id, patch))

    @api.delete("/api/drafts/{draft_id}")
    def delete_draft(draft_id: str) -> dict[str, Any]:
        service.draft_or_404(draft_id)
        service.delete_draft(draft_id)
        return {"ok": True}

    @api.post("/api/drafts/{draft_id}/photos")
    async def add_photos(draft_id: str, photos: list[UploadFile] = File(...)) -> dict[str, Any]:
        files = await _read_photos(photos)
        return draft_full(service, service.add_photos(draft_id, files))

    @api.delete("/api/drafts/{draft_id}/photos/{name}")
    def delete_photo(draft_id: str, name: str) -> dict[str, Any]:
        return draft_full(service, service.delete_photo(draft_id, name))

    @api.get("/api/drafts/{draft_id}/photos/{name}")
    def get_photo(draft_id: str, name: str) -> FileResponse:
        draft = service.draft_or_404(draft_id)
        safe = Path(name).name
        if safe not in draft.photos:
            raise HTTPException(404, "Fotoğraf bulunamadı.")
        return FileResponse(service.paths.draft_dir(draft_id) / safe, headers={"Cache-Control": "max-age=86400"})

    @api.post("/api/drafts/{draft_id}/generate")
    def generate(draft_id: str) -> dict[str, Any]:
        return service.start_generate(draft_id).to_dict()

    @api.post("/api/drafts/{draft_id}/publish")
    def publish(draft_id: str, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.start_publish(draft_id, str(payload.get("platform", "")),
                                     force=bool(payload.get("force", False))).to_dict()

    @api.post("/api/drafts/{draft_id}/research")
    def draft_research(draft_id: str, platform: str = Body("sahibinden", embed=True)) -> dict[str, Any]:
        draft = service.draft_or_404(draft_id)
        query = service.research_query_for(draft)
        return service.start_research(platform, query=query, draft_id=draft_id).to_dict()

    @api.post("/api/title-score")
    def title_score(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        platform = payload.get("platform", "sahibinden")
        if platform not in PLATFORMS:
            raise HTTPException(400, "Bilinmeyen platform")
        title = str(payload.get("title", ""))
        rules = rules_for(platform, service.settings)
        keywords: list[str] = []
        brand = model = ""
        if payload.get("draft_id"):
            draft = service.db.get_draft(payload["draft_id"])
            if draft:
                brand, model = draft.product.brand, draft.product.model
                keywords = [brand, model, *draft.product.keywords]
        cand = score_title(title, rules=rules, keywords=keywords, brand=brand, model=model)
        return {"score": cand.score, "notes": cand.notes, "length": len(title), "max": rules.title_max}

    # ------------------------------------------------------------ işler

    @api.get("/api/jobs")
    def list_jobs(active: bool = False, limit: int = 30) -> list[dict[str, Any]]:
        return [j.to_dict(since=max(0, len(j.logs) - 3)) for j in service.jobs.list(active_only=active, limit=limit)]

    @api.get("/api/jobs/{job_id}")
    def get_job(job_id: str, since: int = 0) -> dict[str, Any]:
        job = service.jobs.get(job_id)
        if not job:
            raise HTTPException(404, "İş bulunamadı.")
        return job.to_dict(since=since)

    @api.post("/api/jobs/{job_id}/respond")
    def respond(job_id: str, value: bool = Body(..., embed=True)) -> dict[str, Any]:
        if not service.jobs.respond(job_id, value):
            raise HTTPException(409, "Bu iş şu an yanıt beklemiyor.")
        return {"ok": True}

    @api.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str) -> dict[str, Any]:
        return {"ok": service.jobs.cancel(job_id)}

    @api.get("/api/jobs/{job_id}/screenshot")
    def screenshot(job_id: str) -> FileResponse:
        job = service.jobs.get(job_id)
        if not job or not job.screenshot or not Path(job.screenshot).exists():
            raise HTTPException(404, "Ekran görüntüsü yok.")
        path = Path(job.screenshot).resolve()
        if service.paths.shots_dir.resolve() not in path.parents:
            raise HTTPException(403, "Geçersiz yol.")
        return FileResponse(path)

    # ------------------------------------------------------------ uzaktan tarayıcı

    def _remote(key: str):  # type: ignore[no-untyped-def]
        # key: hesap profili ("sahibinden") ya da tarama profili ("sahibinden-tarama")
        if key.removesuffix(SCAN_SUFFIX) not in PLATFORMS:
            raise HTTPException(404, "Bilinmeyen platform")
        return service.pool.worker(key).remote

    @api.get("/api/browser/{platform}/state")
    def remote_state(platform: str) -> dict[str, Any]:
        remote = _remote(platform)
        remote.request_frame()
        return remote.state()

    @api.get("/api/browser/{platform}/screen")
    def remote_screen(platform: str) -> Response:
        remote = _remote(platform)
        remote.request_frame()
        if not remote.frame:
            return Response(status_code=204)
        return Response(remote.frame, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @api.post("/api/browser/{platform}/input")
    def remote_input(platform: str, command: dict[str, Any] = Body(...)) -> dict[str, Any]:
        remote = _remote(platform)
        if not remote.active:
            raise HTTPException(409, "Tarayıcı şu an kullanıcı girişi beklemiyor.")
        remote.push(command)
        return {"ok": True}

    # ------------------------------------------------------------ platformlar

    @api.post("/api/platforms/{platform}/login")
    def platform_login(platform: str) -> dict[str, Any]:
        return service.start_login(platform).to_dict()

    @api.delete("/api/platforms/{platform}/cooldown")
    def platform_cooldown_clear(platform: str) -> dict[str, Any]:
        if platform not in PLATFORMS:
            raise HTTPException(404, "Bilinmeyen platform")
        clear_cooldown(service.db, platform)
        return {"ok": True}

    # ------------------------------------------------------------ takip & fırsatlar

    @api.get("/api/watches")
    def list_watches() -> list[dict[str, Any]]:
        out = []
        for w in service.db.list_watches():
            data = w.model_dump()
            running = service.jobs.find_active("scan", watch_id=w.id)
            data["running_job"] = running.id if running else None
            out.append(data)
        return out

    @api.post("/api/watches")
    def create_watch(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.save_watch(payload).model_dump()

    @api.put("/api/watches/{watch_id}")
    def update_watch(watch_id: int, payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.save_watch(payload, watch_id).model_dump()

    @api.delete("/api/watches/{watch_id}")
    def delete_watch(watch_id: int) -> dict[str, Any]:
        service.db.delete_watch(watch_id)
        return {"ok": True}

    @api.post("/api/watches/{watch_id}/scan")
    def scan_watch(watch_id: int) -> dict[str, Any]:
        return service.start_scan(watch_id).to_dict()

    @api.get("/api/deals")
    def list_deals(
        status: str | None = None, min_score: float | None = None, watch_id: int | None = None,
        all: bool = False, limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = service.db.list_deals(status=status, min_score=min_score, watch_id=watch_id,
                                     only_deals=not all, limit=limit)
        return [deal_view(d, listing) for d, listing in rows]

    @api.get("/api/deals/{deal_id}")
    def get_deal(deal_id: int) -> dict[str, Any]:
        deal = service.db.get_deal(deal_id)
        if not deal:
            raise HTTPException(404, "Fırsat bulunamadı.")
        listing = service.db.get_listing(deal.listing_id)
        if not listing:
            raise HTTPException(404, "İlan bulunamadı.")
        view = deal_view(deal, listing)
        view["price_history"] = service.db.price_history(listing.id)
        return view

    @api.put("/api/deals/{deal_id}")
    def update_deal(deal_id: int, status: DealStatus = Body(..., embed=True)) -> dict[str, Any]:
        deal = service.db.set_deal_status(deal_id, status)
        if not deal:
            raise HTTPException(404, "Fırsat bulunamadı.")
        return deal.model_dump()

    @api.post("/api/research")
    def research(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
        return service.start_research(
            payload.get("platform", "sahibinden"), query=payload.get("query", ""), url=payload.get("url", "")
        ).to_dict()

    # ------------------------------------------------------------ arayüz

    api.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @api.get("/manifest.webmanifest", include_in_schema=False)
    def manifest() -> FileResponse:
        return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")

    @api.get("/", include_in_schema=False)
    @api.get("/{path:path}", include_in_schema=False)
    def index(path: str = "") -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "Bulunamadı")
        return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})

    return api


def _parse_price_form(value: str) -> float | None:
    value = (value or "").strip().replace(" ", "")
    if not value:
        return None
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".")
    elif "," in value:
        value = value.replace(",", ".")
    elif value.count(".") >= 1 and len(value.split(".")[-1]) == 3:
        value = value.replace(".", "")
    try:
        return float(value)
    except ValueError as exc:
        raise HTTPException(400, "Fiyat sayısal olmalı (ör. 32500).") from exc
