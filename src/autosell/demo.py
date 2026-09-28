"""Demo modu: API anahtarı olmadan paneli denemek için örnek yapay zekâ ve örnek veriler."""

from __future__ import annotations

import io
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

from PIL import Image, ImageDraw

from .ai.base import ImageInput, LLMProvider
from .listing import ListingGenerator
from .market.deals import evaluate_deal
from .market.pricing import estimate_market
from .models import ScrapedListing, Watch
from .service import AutoSell
from .textutil import normalize


def _listing_payload(notes: str) -> dict[str, Any]:
    n = normalize(notes)
    if "ps5" in n or "playstation" in n:
        product = {
            "ad": "Sony PlayStation 5 Disk Sürümü", "marka": "Sony", "model": "PlayStation 5", "durum": "Çok İyi",
            "one_cikanlar": ["2 kol", "Kutulu", "Faturalı"], "kusurlar": [], "kutu_icerigi": ["Kutu", "2 DualSense kol", "HDMI kablo"],
            "anahtar_kelimeler": ["PS5", "PlayStation 5", "Disk", "2 Kol"], "eksik_bilgiler": ["Garanti bitiş tarihi"],
            "uyarilar": [], "kapak_fotografi": 0,
        }
        path_s = ["İkinci El ve Sıfır Alışveriş", "Oyun & Konsol", "Konsollar", "PlayStation 5"]
        path_l = ["Elektronik", "Oyun & Konsol"]
        titles = ["Sony PS5 Disk Sürümü 2 Kollu Kutulu Faturalı", "PlayStation 5 Disk + 2 DualSense Kol Temiz",
                  "PS5 Disk Sürüm Sorunsuz Kutulu 2 Kol"]
        desc = ("Sony PlayStation 5 disk sürümü, özenle kullanıldı ve sorunsuz çalışıyor.\n\n"
                "Ürün Özellikleri\n• Disk sürümü (Blu-ray)\n• 2 adet DualSense kol\n• 825 GB SSD\n\n"
                "Kutu İçeriği\n• Orijinal kutu, HDMI ve güç kablosu\n\nElden teslim veya kargo ile gönderim yapılabilir.")
        attrs = [{"ad": "Marka", "deger": "Sony"}, {"ad": "Model", "deger": "PlayStation 5"},
                 {"ad": "Durumu", "deger": "İkinci El"}]
    else:
        product = {
            "ad": "Apple iPhone 13 128 GB Mavi", "marka": "Apple", "model": "iPhone 13", "durum": "Çok İyi",
            "one_cikanlar": ["Pil sağlığı %89", "Kutulu", "Faturalı"], "kusurlar": ["Kasa kenarında hafif çizik"],
            "kutu_icerigi": ["Kutu", "Şarj kablosu"], "anahtar_kelimeler": ["iPhone 13", "128 GB", "Mavi", "Kutulu"],
            "eksik_bilgiler": ["Garanti bitiş tarihi", "Alım tarihi"], "uyarilar": [], "kapak_fotografi": 0,
        }
        path_s = ["İkinci El ve Sıfır Alışveriş", "Cep Telefonu", "Modeller", "Apple", "iPhone 13"]
        path_l = ["Cep Telefonu & Aksesuar", "Cep Telefonu"]
        titles = ["Apple iPhone 13 128 GB Mavi Kutulu Faturalı", "iPhone 13 128GB Mavi Pil %89 Temiz",
                  "Temiz iPhone 13 128 GB - Kutulu, Faturalı", "iPhone 13 128 GB Mavi Hatasız Az Kullanılmış"]
        desc = ("iPhone 13 128 GB Mavi, ilk sahibinden ve özenle kullanıldı.\n\n"
                "Ürün Özellikleri\n• 128 GB dahili hafıza\n• Pil sağlığı %89\n• Face ID ve tüm fonksiyonlar sorunsuz\n\n"
                "Durumu\n• Ekran çiziksiz, kasa kenarında hafif kullanım izi var\n\n"
                "Kutu İçeriği\n• Orijinal kutu ve şarj kablosu, fatura mevcut\n\n"
                "Elden teslim veya kargo ile gönderim yapılabilir.")
        attrs = [{"ad": "Dahili Hafıza", "deger": "128 GB"}, {"ad": "Renk", "deger": "Mavi"},
                 {"ad": "Garanti", "deger": "Hayır"}, {"ad": "Durumu", "deger": "İkinci El"}]
    return {
        "urun": product,
        "sahibinden": {"kategori_yolu": path_s, "baslik_adaylari": titles, "aciklama": desc, "ozellikler": attrs},
        "letgo": {"kategori_yolu": path_l, "baslik_adaylari": titles,
                  "aciklama": "✨ " + desc.replace("Ürün Özellikleri\n", "").replace("Kutu İçeriği\n", ""),
                  "ozellikler": attrs},
    }


class DemoProvider(LLMProvider):
    """Gerçek API çağırmadan örnek yanıtlar üreten sahte sağlayıcı."""

    name = "demo"
    model = "ornek-yanitlar"
    supports_images = True

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        schema: dict[str, Any],
        images: Sequence[ImageInput] = (),
        web_search: bool = False,
        max_tokens: int = 16000,
    ) -> dict[str, Any]:
        props = schema.get("properties", {})
        if "urun" in props:
            data = _listing_payload(prompt)
            return {k: v for k, v in data.items() if k in props}
        if "secim" in props:
            options = [o for o in props["secim"].get("enum", []) if o != "YOK"]
            return {"secim": options[0] if options else "YOK", "gerekce": "demo"}
        if "eylem" in props:
            return {"eylem": "kullanici", "oge": "", "deger": "", "aciklama": "Demo modunda ajan kullanılmaz."}
        if "firsat_mi" in props:
            return {
                "ayni_urun_emsal_orani": 0.8, "duzeltilmis_piyasa_degeri": 31500, "hizli_satis_fiyati": 30500,
                "tahmini_net_kar": 3800, "risk_seviyesi": "dusuk", "riskler": [], "firsat_mi": True,
                "pazarlik_teklifi": 25000,
                "yorum": "Emsallerin belirgin şekilde altında. 25.000 TL'ye pazarlık denenebilir; IMEI kaydını ve "
                         "pil sağlığını teslimatta kontrol edin.",
                "kaynaklar": [],
            }
        if "cevap" in props:
            return {"cevap": "tamam"}
        return {k: "" for k in props}


def placeholder_photo(text: str, color: tuple[int, int, int]) -> bytes:
    img = Image.new("RGB", (900, 900), color)
    draw = ImageDraw.Draw(img)
    for i in range(0, 900, 6):  # hafif degrade
        shade = tuple(max(0, c - i // 12) for c in color)
        draw.line([(0, i), (900, i)], fill=shade, width=6)
    draw.rounded_rectangle([300, 150, 600, 750], radius=48, outline=(255, 255, 255), width=10)
    draw.text((330, 790), text[:28], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return buf.getvalue()


DEMO_MARKET = [
    ("iPhone 13 128 GB Mavi Temiz", 31000), ("iPhone 13 128GB Kutulu Faturalı", 32500),
    ("Sahibinden iPhone 13 128 GB Gece Yarısı", 30500), ("iPhone 13 128 GB pil %90", 33000),
    ("iphone 13 128gb beyaz hatasız", 31500), ("iPhone 13 128 GB Yeşil", 29900),
    ("iPhone 13 256 GB Pembe", 36000), ("iPhone 13 Pro 128 GB", 41000), ("iPhone 13 Kılıf Şeffaf", 250),
    ("iPhone 13 128 GB Kırmızı", 32000), ("iPhone 13 128 GB acil satılık", 25900),
    ("iPhone 13 128 GB kapora ile gönderilir", 14500), ("iPhone 13 128 GB Yıldız Işığı", 30900),
]


def seed_demo(app: AutoSell) -> None:
    """Boş veritabanına örnek taslak, takip listesi ve fırsatlar ekler."""
    if app.db.list_drafts() or app.db.list_watches():
        return
    app.provider_override = app.provider_override or DemoProvider()
    settings = app.settings
    if not settings.seller.city:
        app.settings_store.update({"seller": {"city": "İstanbul", "district": "Kadıköy", "neighborhood": "Moda Mah."}})
        settings = app.settings

    phone = app.create_draft(
        notes="iPhone 13 128GB mavi, pil %89, kutusu faturası var. Kasada ufak çizik.",
        price=32500,
        photos=[("1.jpg", placeholder_photo("iPhone 13", (40, 90, 200))),
                ("2.jpg", placeholder_photo("iPhone 13 arka", (30, 60, 150)))],
    )
    ListingGenerator(app.provider_override, settings).generate(phone, app.photo_paths(phone))
    app.db.save_draft(phone)
    ps5 = app.create_draft(
        notes="PS5 disk sürümü, 2 kol, kutulu faturalı", price=21000,
        photos=[("1.jpg", placeholder_photo("PlayStation 5", (25, 25, 35)))],
    )
    ListingGenerator(app.provider_override, settings).generate(ps5, app.photo_paths(ps5))
    app.db.save_draft(ps5)

    watch = app.db.save_watch(Watch(name="iPhone 13 128 GB", platform="sahibinden", query="iPhone 13 128 GB",
                                    price_max=40000, min_profit=2000, min_margin_pct=8, interval_min=15))
    app.db.save_watch(Watch(name="PS5 fırsatları", platform="letgo", query="ps5", min_profit=1500,
                            interval_min=20, active=False))
    rnd = random.Random(7)
    base = datetime.now(timezone.utc) - timedelta(days=3)
    listings = []
    for i, (title, price) in enumerate(DEMO_MARKET):
        seen = (base + timedelta(hours=i * 5)).replace(microsecond=0).isoformat()
        item = ScrapedListing(
            platform="sahibinden", external_id=str(1134567890 + i), title=title, price=price,
            url=f"https://www.sahibinden.com/ilan/demo-{1134567890 + i}/detay",
            location=rnd.choice(["İstanbul / Kadıköy", "İstanbul / Beşiktaş", "Ankara / Çankaya", "İzmir / Bornova"]),
            date_text="28 Eylül 2026",
        )
        listing, _ = app.db.upsert_listing(item, watch.id, seen)
        listings.append(listing)
    drop = ScrapedListing(platform="sahibinden", external_id=str(1134567890 + 10), title=DEMO_MARKET[10][0],
                          price=24900, url=listings[10].url, location=listings[10].location)
    listings[10], _ = app.db.upsert_listing(drop, watch.id)
    comps = app.db.listings_for_watch(watch.id or 0)
    for listing in listings:
        est = estimate_market(listing.title, comps, exclude_id=listing.id)
        deal = evaluate_deal(listing, est, settings.market, watch)
        if deal.comps_count:
            if deal.is_deal:
                deal.ai = DemoProvider().generate_json(system="", prompt="", schema={"properties": {"firsat_mi": {}}})
            app.db.save_deal(deal)
    watch.last_run_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    watch.last_status = "13 ilan, 13 yeni, 1 fiyat değişikliği (demo)"
    app.db.save_watch(watch)
