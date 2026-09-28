"""Alan modelleri: ilan taslakları, piyasa ilanları, takip listeleri ve fırsatlar."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str = "") -> str:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}{stamp}-{secrets.token_hex(3)}"


# --------------------------------------------------------------------------- ilan


class Attribute(BaseModel):
    name: str
    value: str


class TitleCandidate(BaseModel):
    text: str
    score: float = 0.0
    notes: list[str] = Field(default_factory=list)


class ProductInfo(BaseModel):
    name: str = ""
    brand: str = ""
    model: str = ""
    condition: str = ""
    highlights: list[str] = Field(default_factory=list)
    defects: list[str] = Field(default_factory=list)
    included: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


PublicationState = Literal["bekliyor", "calisiyor", "onay_bekliyor", "yayinda", "hata", "iptal"]


class PublicationStatus(BaseModel):
    status: PublicationState = "bekliyor"
    url: str = ""
    listing_no: str = ""
    message: str = ""
    job_id: str = ""
    updated_at: str = Field(default_factory=now_iso)


class PlatformListing(BaseModel):
    category_path: list[str] = Field(default_factory=list)
    title: str = ""
    title_candidates: list[TitleCandidate] = Field(default_factory=list)
    description: str = ""
    attributes: list[Attribute] = Field(default_factory=list)
    # Boşsa taslağın genel fiyatı kullanılır.
    price: float | None = None


class Draft(BaseModel):
    id: str = Field(default_factory=lambda: new_id("ilan-"))
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
    notes: str = ""
    price: float | None = None
    currency: str = "TL"
    platforms: list[str] = Field(default_factory=lambda: ["sahibinden", "letgo"])
    photos: list[str] = Field(default_factory=list)
    product: ProductInfo = Field(default_factory=ProductInfo)
    listings: dict[str, PlatformListing] = Field(default_factory=dict)
    publications: dict[str, PublicationStatus] = Field(default_factory=dict)
    generated: bool = False
    ai_model: str = ""
    last_error: str = ""

    def price_for(self, platform: str) -> float | None:
        listing = self.listings.get(platform)
        if listing and listing.price is not None:
            return listing.price
        return self.price

    def display_title(self) -> str:
        for platform in self.platforms:
            listing = self.listings.get(platform)
            if listing and listing.title:
                return listing.title
        return self.product.name or (self.notes.strip().splitlines() or ["Yeni ilan"])[0][:60]


# ------------------------------------------------------------------------ piyasa


class ScrapedListing(BaseModel):
    """Arama sonuç sayfasından okunan tek ilan kartı."""

    platform: str
    external_id: str
    url: str
    title: str
    price: float | None = None
    currency: str = "TL"
    location: str = ""
    date_text: str = ""
    image_url: str = ""


class MarketListing(ScrapedListing):
    id: int
    first_seen: str
    last_seen: str
    seen_count: int = 1
    prev_price: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)

    @property
    def price_drop(self) -> float | None:
        if self.prev_price and self.price and self.price < self.prev_price:
            return self.prev_price - self.price
        return None


class Watch(BaseModel):
    id: int | None = None
    name: str
    platform: Literal["sahibinden", "letgo"] = "sahibinden"
    query: str = ""
    # Sitede filtrelenmiş bir arama yapıp adres çubuğundaki bağlantıyı yapıştırmak en güvenilir yol.
    search_url: str = ""
    price_min: float | None = None
    price_max: float | None = None
    include_words: list[str] = Field(default_factory=list)
    exclude_words: list[str] = Field(default_factory=list)
    min_profit: float = 1000.0
    min_margin_pct: float = 12.0
    interval_min: int = 15
    active: bool = True
    last_run_at: str | None = None
    last_status: str = ""
    last_found: int = 0
    created_at: str = Field(default_factory=now_iso)


class CompRef(BaseModel):
    listing_id: int
    title: str
    price: float
    similarity: float
    url: str = ""


class MarketEstimate(BaseModel):
    n: int = 0
    median: float | None = None
    p25: float | None = None
    p75: float | None = None
    low: float | None = None
    high: float | None = None
    resale: float | None = None
    mean_similarity: float = 0.0
    confidence: float = 0.0
    comps: list[CompRef] = Field(default_factory=list)


class RiskFlag(BaseModel):
    level: Literal["yuksek", "orta", "dusuk"]
    text: str


DealStatus = Literal["yeni", "incelendi", "favori", "gizli"]


class Deal(BaseModel):
    id: int | None = None
    listing_id: int
    watch_id: int | None = None
    score: float = 0.0
    is_deal: bool = False
    est_value: float | None = None
    resale_price: float | None = None
    buy_price: float | None = None
    est_profit: float | None = None
    margin_pct: float | None = None
    confidence: float = 0.0
    comps_count: int = 0
    risk_flags: list[RiskFlag] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    comps: list[CompRef] = Field(default_factory=list)
    ai: dict[str, Any] | None = None
    status: DealStatus = "yeni"
    notified: bool = False
    created_at: str = Field(default_factory=now_iso)
    updated_at: str = Field(default_factory=now_iso)
