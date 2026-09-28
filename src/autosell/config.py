"""Uygulama ayarları.

Ayarlar ``<veri dizini>/ayarlar.json`` dosyasında tutulur ve web panelinden
düzenlenir. API anahtarları gibi gizli değerler dosyada boş bırakılırsa ortam
değişkenlerinden okunur (ANTHROPIC_API_KEY, OPENAI_API_KEY, TELEGRAM_BOT_TOKEN,
TELEGRAM_CHAT_ID, AUTOSELL_PANEL_PASSWORD).
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
        post_url="",
        search_url_template="https://www.letgo.com/arama?q={q}",
        newest_sort_param="",
        listing_url_patterns=[
            r"-iid-(\d{5,})",
            r"/item/[^\s?#]*?(\d{6,})",
            r"/ilan/[^\s?#]*?(\d{6,})",
            r"/i/[^/\s?#]+_([0-9a-fA-F-]{8,})",
        ],
        card_selectors={
            "card": '[data-aut-id="itemBox"]',
            "title": '[data-aut-id="itemTitle"]',
            "price": '[data-aut-id="itemPrice"]',
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
    default_interval_min: int = 20
    min_interval_min: int = 10
    max_pages: int = 2
    # Her taramada detay sayfası açılacak en iyi aday sayısı
    fetch_details: int = 2
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
        return Settings.model_validate(deep_merge(base, data))

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
