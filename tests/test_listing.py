from autosell.config import Settings
from autosell.listing import ListingGenerator, basic_listing, rules_for, score_title
from autosell.models import Draft

from .conftest import FakeProvider


def _ai_response():
    platform = {
        "kategori_yolu": ["İkinci El ve Sıfır Alışveriş", "Cep Telefonu", "Modeller", "Apple", "iPhone 13"],
        "baslik_adaylari": [
            "iphone 13",  # çok kısa
            "SAHİBİNDEN ACİL ACİL İPHONE 13!!! 0532 111 22 33",  # kural dışı
            "Apple iPhone 13 128 GB Mavi Kutulu Faturalı Pil %89",
            "Temiz iPhone 13 128GB - Garantili, Kutulu, Hatasız ve Çok Temiz Kullanılmış",
        ],
        "aciklama": "Tertemiz iPhone 13.\n\n• 128 GB\n• Pil %89\n\nDetay için www.site.com veya 0532 111 22 33",
        "ozellikler": [
            {"ad": "Dahili Hafıza", "deger": "128 GB"},
            {"ad": "Renk", "deger": "Mavi"},
            {"ad": "", "deger": "boş etiket atlanmalı"},
        ],
    }
    return {
        "urun": {
            "ad": "Apple iPhone 13 128 GB",
            "marka": "Apple",
            "model": "iPhone 13",
            "durum": "Çok İyi",
            "one_cikanlar": ["Pil %89", "Kutulu"],
            "kusurlar": ["Kasada hafif çizik"],
            "kutu_icerigi": ["Kutu", "Kablo"],
            "anahtar_kelimeler": ["iPhone 13", "128 GB", "Mavi", "Kutulu"],
            "eksik_bilgiler": ["Garanti bitiş tarihi"],
            "uyarilar": [],
            "kapak_fotografi": 1,
        },
        "sahibinden": platform,
        "letgo": dict(platform, aciklama="Temiz telefon 👍 Pil %89"),
    }


def test_title_score_prefers_informative_titles():
    rules = rules_for("sahibinden", Settings())
    good = score_title("Apple iPhone 13 128 GB Mavi Kutulu Faturalı", rules=rules,
                       keywords=["iPhone 13", "128 GB"], brand="Apple", model="iPhone 13")
    spam = score_title("ACİL ACİL İPHONE 13 İPHONE 13!!!", rules=rules,
                       keywords=["iPhone 13", "128 GB"], brand="Apple", model="iPhone 13")
    assert good.score > spam.score + 30
    assert any("Tekrarlanan" in n for n in spam.notes)


def test_generator_builds_platform_listings(make_photo):
    settings = Settings()
    settings.seller.seller_type = "Sahibinden"
    photos = [make_photo("a.jpg"), make_photo("b.jpg", (200, 30, 30))]
    draft = Draft(notes="iPhone 13 128GB mavi, pil %89, kutulu", price=32500, photos=["a.jpg", "b.jpg"])
    provider = FakeProvider(_ai_response())

    ListingGenerator(provider, settings).generate(draft, photos)

    call = provider.calls[0]
    assert call["images"] == 2
    assert "32.500 TL" in call["prompt"]
    assert set(call["schema"]["properties"]) == {"urun", "sahibinden", "letgo"}

    sah = draft.listings["sahibinden"]
    assert sah.title == "Apple iPhone 13 128 GB Mavi Kutulu Faturalı"
    assert all(len(c.text) <= 50 for c in sah.title_candidates)
    assert all("0532" not in c.text for c in sah.title_candidates)
    assert "www.site.com" not in sah.description and "0532" not in sah.description
    names = [a.name for a in sah.attributes]
    assert names == ["Dahili Hafıza", "Renk", "Kimden", "Takas"]
    assert sah.category_path[-1] == "iPhone 13"
    # letgo emojiye izin veriyor, sahibinden vermiyor
    assert "👍" in draft.listings["letgo"].description
    assert draft.photos == ["b.jpg", "a.jpg"]  # kapak fotoğrafı öne alındı
    assert draft.product.defects == ["Kasada hafif çizik"]
    assert draft.generated and draft.ai_model == "sahte:test-model"


def test_generator_tolerates_incomplete_ai_output(make_photo):
    settings = Settings()
    draft = Draft(notes="Koltuk takımı 3+3+1", platforms=["letgo"])
    provider = FakeProvider({"urun": {"ad": "Koltuk Takımı"}, "letgo": {"baslik_adaylari": []}})
    ListingGenerator(provider, settings).generate(draft, [make_photo()])
    assert draft.listings["letgo"].title == "Koltuk Takımı"
    assert draft.listings["letgo"].attributes[-1].name == "Takas"


def test_basic_listing_without_ai():
    settings = Settings()
    draft = Draft(notes="Bisiklet 26 jant\nAz kullanıldı, bakımlı.", platforms=["sahibinden"])
    basic_listing(draft, settings)
    listing = draft.listings["sahibinden"]
    assert listing.title == "Bisiklet 26 Jant"
    assert "Az kullanıldı" in listing.description
