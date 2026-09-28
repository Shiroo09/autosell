"""Uygulama ayarları.

Ayarlar ``<veri dizini>/ayarlar.json`` dosyasında tutulur ve web panelinden
düzenlenir. API anahtarları gibi gizli değerler dosyada boş bırakılırsa ortam
değişkenlerinden okunur (ANTHROPIC_API_KEY, OPENAI_API_KEY, LAYA_API_KEY,
TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, AUTOSELL_PANEL_PASSWORD).
"""

from __future__ import annotations

import copy
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

PLATFORMS: tuple[str, ...] = ("sahibinden", "letgo")
PLATFORM_NAMES = {"sahibinden": "Sahibinden", "letgo": "Letgo"}

DEFAULT_CLAUDE_MODEL = "claude-opus-5-5"

# Web panelinin maskelediği gizli alanlar (bölüm, alan)
SECRET_FIELDS: tuple[tuple[str, str], ...] = (
    ("ai", "claude_api_key"),
    ("ai", "openai_api_key"),
    ("decision", "api_key"),
    ("notify", "telegram_token"),
    ("web", "password"),
)
MASK_PREFIX = "••••"


DEFAULT_OPENAI_BASE_URL = "https://betaapiv2.llmapi.art/v1"
DEFAULT_OPENAI_MODEL = "muse-spark-1.3"


class AISettings(BaseModel):
    provider: Literal["claude", "openai"] = "openai"
    claude_model: str = DEFAULT_CLAUDE_MODEL
    claude_effort: Literal["low", "medium", "high", "xhigh", "max"] = "high"
    claude_api_key: str = ""
    # Güvenlik sınıflandırıcısı isteği reddederse Anthropic'in önerdiği modelle
    # sunucu tarafında yeniden dene (server-side fallback).
    claude_fallback: bool = True
    openai_base_url: str = DEFAULT_OPENAI_BASE_URL
    openai_model: str = DEFAULT_OPENAI_MODEL
    openai_api_key: str = ""
    openai_vision: bool = True
    max_photos: int = 6
    # Fırsat değerlendirmede Claude'un web araması ile güncel fiyat araştırması
    web_research: bool = False


class DecisionSettings(BaseModel):
    """Hızlı karar motoru (Jev / Laya): fırsat adaylarını saniyeler içinde süzer."""

    # "jev": API ağ geçidindeki TypeSafe Jev, "laya": bilgisayarda çalışan laya-serve, "kapali": kullanma
    engine: Literal["jev", "laya", "kapali"] = "jev"
    # Boşsa jev için yapay zekâ ağ geçidi (OpenAI base URL), laya için http://127.0.0.1:8000
    base_url: str = ""
    # Boşsa jev için OpenAI uyumlu API anahtarı, laya için LAYA_API_KEY (tanımlıysa) kullanılır
    api_key: str = ""
    # Boşsa jev için "jev", laya için "multilingual" (Türkçe için doğru model)
    model: str = ""
    # Her taramada hızlı kararla incelenecek en fazla aday
    max_checks: int = 12
    # Bu olasılığın üstündeki "aksesuar / farklı ürün / kusurlu / şüpheli" kararları ilanı eler
    threshold: float = 0.6
    timeout_s: float = 20.0


class SellerSettings(BaseModel):
    city: str = ""
    district: str = ""
    neighborhood: str = ""
    seller_type: str = "Sahibinden"
    allow_trade: bool = False
    negotiable: bool = True
    delivery_note: str = "Elden teslim veya kargo ile gönderim yapılabilir."
    signature: str = ""


class WritingSettings(BaseModel):
    title_style: Literal["title", "upper", "sentence"] = "title"
    tone: Literal["dengeli", "samimi", "profesyonel"] = "dengeli"
    extra_instructions: str = ""


class PlatformSettings(BaseModel):
    enabled: bool = True
    # False ise form doldurulur, son "Yayınla" adımında kullanıcı onayı beklenir.
    auto_publish: bool = False
    # Hesap güvenliği: son 24 saatte en fazla ilan sayısı ve iki ilan arası en az bekleme (dk)
    max_publish_per_day: int = 5
    min_minutes_between_publish: int = 15
    # Aynı/çok benzer ilanın tekrar verilmesini engelleme süresi (gün; mükerrer ilan kuralı)
    duplicate_days: int = 30
    title_max: int = 60
    description_max: int = 4000
    use_emoji: bool = False
    home_url: str = ""
    login_url: str = ""
    # Boşsa ana sayfadaki "İlan Ver" / "Sat" düğmesine tıklanır.
    post_url: str = ""
    # {q} yer tutucusu arama kelimesiyle değiştirilir.
    search_url_template: str = ""
    # Arama sonuçlarını en yeniye göre sıralayan sorgu parametresi (ör. sorting=date_desc)
    newest_sort_param: str = ""
    # İlan detay bağlantılarını tanıyan düzenli ifadeler; ilk grup ilan numarasıdır.
    listing_url_patterns: list[str] = Field(default_factory=list)
    # Arama sonuç kartları için CSS seçicileri (card, title, price, location, date, image, id_attr)
    card_selectors: dict[str, str] = Field(default_factory=dict)


def default_sahibinden() -> PlatformSettings:
    return PlatformSettings(
        title_max=50,
        description_max=6000,
        use_emoji=False,
        home_url="https://www.sahibinden.com/",
        login_url="https://secure.sahibinden.com/giris",
        post_url="",
        search_url_template="https://www.sahibinden.com/arama?query_text={q}",
        newest_sort_param="sorting=date_desc",
        listing_url_patterns=[r"/ilan/[^\s?#]*?-(\d{6,})/detay"],
        card_selectors={
            "card": "tr.searchResultsItem[data-id]",
            "id_attr": "data-id",
            "title": "a.classifiedTitle",
            "price": "td.searchResultsPriceValue",
            "date": "td.searchResultsDateValue",
            "location": "td.searchResultsLocationValue",
            "image": "td.searchResultsLargeThumbnail img",
        },
    )


def default_letgo() -> PlatformSettings:
    return PlatformSettings(
        title_max=70,
        description_max=4000,
        use_emoji=True,
        home_url="https://www.letgo.com/",
        login_url="https://www.letgo.com/",
        post_url="https://www.letgo.com/ilan-ver",
        search_url_template="https://www.letgo.com/arama?query_text={q}&isSearchCall=true",
        newest_sort_param="sorting=desc-creation",
        listing_url_patterns=[
            r"-iid-(\d{5,})",
            r"/item/[^\s?#]*?(\d{6,})",
            r"/ilan/[^\s?#]*?(\d{6,})",
            r"/i/[^/\s?#]+_([0-9a-fA-F-]{8,})",
        ],
        # Eylül 2026 letgo tasarımı; eski tasarımın (data-aut-id) seçicileri yedek olarak "||" ile denenir.
        card_selectors={
            "card": '[data-testid="item-card"]',
            "title": '[data-slot="item-card-image"] img@alt || [data-slot="item-card-body"] div.line-clamp-1'
                     ' || [data-aut-id="itemTitle"]',
            "price": '[data-slot="item-card-body"] p || [data-aut-id="itemPrice"]',
            "location": '[data-aut-id="item-location"]',
            "date": '[data-aut-id="item-date"]',
            "image": "img",
        },
    )


class BrowserSettings(BaseModel):
    headless: bool = False
    # "" = Playwright Chromium, "chrome" / "msedge" = bilgisayarda kurulu tarayıcı
    channel: str = ""
    executable_path: str = ""
    slow_mo_ms: int = 60
    # Siteyi yormamak için eylemler arası bekleme aralığı (ms)
    min_delay_ms: int = 300
    max_delay_ms: int = 900
    # Giriş, doğrulama kodu, onay gibi kullanıcı adımları için azami bekleme (sn)
    human_timeout_s: int = 600
    # Sezgisel yöntemler takıldığında yapay zekâya adım adım karar verdirme
    use_ai_agent: bool = True
    agent_max_steps: int = 20


class MarketSettings(BaseModel):
    default_interval_min: int = 5
    min_interval_min: int = 2
    # Tarama aralıkları bu oranda (±%) rastgele kaydırılır; istekler makine düzeninde gitmez
    interval_jitter_pct: float = 20.0
    # Derin taramada okunacak sayfa sayısı; arada yalnızca en yeniye sıralı ilk sayfalar okunur
    max_pages: int = 2
    quick_pages: int = 1
    deep_scan_hours: float = 6.0
    # Her taramada detay sayfası açılacak en iyi aday sayısı
    fetch_details: int = 2
    # Platform başına son bir saatte en fazla sayfa isteği (arama + detay). Siteye insan
    # hızından fazla istek gitmez; aşılırsa taramalar sıraya girer. 0 = sınırsız (önerilmez).
    hourly_request_budget: int = 60
    # Tarama tarayıcısı resim ve video indirmez (sayfalar çok daha hızlı açılır)
    block_images: bool = True
    # Site CAPTCHA / erişim engeli gösterirse o platformun taraması bu kadar dakika duraklatılır
    block_cooldown_min: int = 90
    # Her taramada yapay zekâ ile değerlendirilecek en iyi aday sayısı
    ai_evaluations: int = 2
    # Alırken yapılabilecek tahmini pazarlık indirimi (%)
    negotiation_pct: float = 5.0
    # Satarken ödenen komisyon (%) ve sabit masraf (kargo, yol vb. TL)
    commission_pct: float = 0.0
    fixed_cost: float = 0.0
    # Hızlı satış için hedeflenen emsal fiyat yüzdeliği
    resale_percentile: float = 45.0
    min_comps: int = 4
    comp_days: int = 45


class NotifySettings(BaseModel):
    telegram_token: str = ""
    telegram_chat_id: str = ""
    min_score: float = 65.0


class WebSettings(BaseModel):
    password: str = ""


class Settings(BaseModel):
    ai: AISettings = Field(default_factory=AISettings)
    decision: DecisionSettings = Field(default_factory=DecisionSettings)
    seller: SellerSettings = Field(default_factory=SellerSettings)
    writing: WritingSettings = Field(default_factory=WritingSettings)
    sahibinden: PlatformSettings = Field(default_factory=default_sahibinden)
    letgo: PlatformSettings = Field(default_factory=default_letgo)
    browser: BrowserSettings = Field(default_factory=BrowserSettings)
    market: MarketSettings = Field(default_factory=MarketSettings)
    notify: NotifySettings = Field(default_factory=NotifySettings)
    web: WebSettings = Field(default_factory=WebSettings)

    def platform(self, name: str) -> PlatformSettings:
        if name not in PLATFORMS:
            raise KeyError(f"Bilinmeyen platform: {name}")
        return getattr(self, name)

    # Gizli değerler: dosyadaki değer boşsa ortam değişkeni kullanılır.
    def telegram_token(self) -> str:
        return self.notify.telegram_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")

    def telegram_chat_id(self) -> str:
        return self.notify.telegram_chat_id or os.environ.get("TELEGRAM_CHAT_ID", "")

    def panel_password(self) -> str:
        return self.web.password or os.environ.get("AUTOSELL_PANEL_PASSWORD", "")

    def decision_endpoint(self) -> tuple[str, str, str] | None:
        """Karar motorunun (adres, anahtar, model) üçlüsü; kapalıysa None."""
        d = self.decision
        if d.engine == "kapali":
            return None
        if d.engine == "jev":
            base = d.base_url.strip() or self.ai.openai_base_url.strip()
            key = d.api_key.strip() or self.ai.openai_api_key.strip() or os.environ.get("OPENAI_API_KEY", "")
            return base, key, d.model.strip() or "jev"
        from .ai.decision import DEFAULT_LAYA_URL

        base = d.base_url.strip() or DEFAULT_LAYA_URL
        return base, d.api_key.strip() or os.environ.get("LAYA_API_KEY", ""), d.model.strip() or "multilingual"


@dataclass(frozen=True)
class Paths:
    root: Path

    @property
    def settings_file(self) -> Path:
        return self.root / "ayarlar.json"

    @property
    def db_file(self) -> Path:
        return self.root / "autosell.db"

    @property
    def drafts_dir(self) -> Path:
        return self.root / "ilanlar"

    @property
    def browser_dir(self) -> Path:
        return self.root / "tarayici"

    @property
    def shots_dir(self) -> Path:
        return self.root / "ekran"

    def draft_dir(self, draft_id: str) -> Path:
        return self.drafts_dir / draft_id

    def ensure(self) -> "Paths":
        for d in (self.root, self.drafts_dir, self.browser_dir, self.shots_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


def resolve_paths(data_dir: str | os.PathLike[str] | None = None) -> Paths:
    raw = data_dir or os.environ.get("AUTOSELL_DATA_DIR") or "veri"
    return Paths(Path(raw).expanduser().resolve()).ensure()


# Ortam değişkenleri kod varsayılanlarının üzerine yazar; panelden kaydedilen ayarlar ise
# ortam değişkenlerinin de üzerine yazar (dosya > ortam > kod).
ENV_DEFAULTS: tuple[tuple[str, str, str], ...] = (
    ("AUTOSELL_AI_PROVIDER", "ai", "provider"),
    ("OPENAI_BASE_URL", "ai", "openai_base_url"),
    ("AUTOSELL_OPENAI_MODEL", "ai", "openai_model"),
    ("AUTOSELL_CLAUDE_MODEL", "ai", "claude_model"),
    ("AUTOSELL_DECISION_ENGINE", "decision", "engine"),
    ("AUTOSELL_DECISION_URL", "decision", "base_url"),
)


def env_defaults() -> dict[str, Any]:
    out: dict[str, Any] = {}
    for env, section, field in ENV_DEFAULTS:
        value = os.environ.get(env, "").strip()
        if value:
            out.setdefault(section, {})[field] = value
    return out


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


# Sitelerin değişmesiyle geçersiz kalan eski varsayılanlar. Kayıtlı ayar hâlâ eski varsayılanı
# taşıyorsa (kullanıcı değiştirmemişse) yenisiyle değiştirilir.
_OLD_LETGO_SEARCH = "https://www.letgo.com/arama?q={q}"
_OLD_LETGO_CARDS = {
    "card": '[data-aut-id="itemBox"]',
    "title": '[data-aut-id="itemTitle"]',
    "price": '[data-aut-id="itemPrice"]',
    "location": '[data-aut-id="item-location"]',
    "date": '[data-aut-id="item-date"]',
    "image": "img",
}


def migrate_settings(data: dict[str, Any]) -> dict[str, Any]:
    letgo = data.get("letgo")
    if isinstance(letgo, dict) and letgo.get("search_url_template") == _OLD_LETGO_SEARCH:
        fresh = default_letgo()
        letgo["search_url_template"] = fresh.search_url_template
        if not letgo.get("newest_sort_param"):
            letgo["newest_sort_param"] = fresh.newest_sort_param
        if not letgo.get("post_url"):
            letgo["post_url"] = fresh.post_url
        if letgo.get("card_selectors") in (None, {}, _OLD_LETGO_CARDS):
            letgo["card_selectors"] = dict(fresh.card_selectors)
    return data


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return MASK_PREFIX + value[-4:] if len(value) > 8 else MASK_PREFIX


class SettingsStore:
    """Ayar dosyasını iş parçacığı güvenli şekilde okur/yazar."""

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.RLock()
        self._cached: Settings | None = None
        self._mtime: float | None = None

    def get(self) -> Settings:
        with self._lock:
            mtime = self.path.stat().st_mtime if self.path.exists() else None
            if self._cached is None or mtime != self._mtime:
                self._cached = self._load()
                self._mtime = mtime
            return self._cached.model_copy(deep=True)

    def _load(self) -> Settings:
        base = deep_merge(Settings().model_dump(), env_defaults())
        if not self.path.exists():
            return Settings.model_validate(base)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"Ayar dosyası okunamadı ({self.path}): {exc}") from exc
        return Settings.model_validate(deep_merge(base, migrate_settings(data)))

    def save(self, settings: Settings) -> Settings:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(settings.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            tmp.replace(self.path)
            try:
                os.chmod(self.path, 0o600)  # API anahtarları içerebilir
            except OSError:
                pass
            self._cached = None
            return self.get()

    def update(self, patch: dict[str, Any]) -> Settings:
        """Kısmi güncelleme. Maskeli gizli değerler (••••) mevcut değeri korur."""
        with self._lock:
            current = self.get().model_dump()
            patch = copy.deepcopy(patch)
            for section, field in SECRET_FIELDS:
                value = patch.get(section, {}).get(field) if isinstance(patch.get(section), dict) else None
                if isinstance(value, str) and value.startswith(MASK_PREFIX):
                    patch[section].pop(field)
            merged = deep_merge(current, patch)
            return self.save(Settings.model_validate(merged))

    def public_dict(self) -> dict[str, Any]:
        """Web paneline gönderilecek, gizli değerleri maskelenmiş ayarlar."""
        settings = self.get()
        data = settings.model_dump()
        env_fallbacks = {
            ("ai", "claude_api_key"): os.environ.get("ANTHROPIC_API_KEY", ""),
            ("ai", "openai_api_key"): os.environ.get("OPENAI_API_KEY", ""),
            ("decision", "api_key"): os.environ.get("LAYA_API_KEY", ""),
            ("notify", "telegram_token"): os.environ.get("TELEGRAM_BOT_TOKEN", ""),
            ("web", "password"): os.environ.get("AUTOSELL_PANEL_PASSWORD", ""),
        }
        secrets: dict[str, dict[str, Any]] = {}
        for section, field in SECRET_FIELDS:
            value = data[section][field]
            data[section][field] = mask_secret(value)
            secrets[f"{section}.{field}"] = {
                "set": bool(value),
                "from_env": not value and bool(env_fallbacks[(section, field)]),
            }
        data["_secrets"] = secrets
        return data
