"""Arama sonuç kartı okuyucusu: platform seçicileri ve genel (bağlantı tabanlı) yöntem."""

import pytest
from playwright.sync_api import sync_playwright

from autosell.config import default_letgo, default_sahibinden
from autosell.market.extract import extract_cards, extract_details, parse_card

SAHIBINDEN_HTML = """
<table id="searchResultsTable"><tbody>
<tr class="searchResultsItem" data-id="1134567890">
  <td class="searchResultsLargeThumbnail"><a href="/ilan/apple-iphone-13-128-gb-1134567890/detay"><img src="/t1.jpg"></a></td>
  <td class="searchResultsTitleValue"><a class="classifiedTitle" href="/ilan/apple-iphone-13-128-gb-1134567890/detay">iPhone 13 128 GB Mavi</a></td>
  <td class="searchResultsPriceValue"><span>32.500 TL</span></td>
  <td class="searchResultsDateValue"><span>28 Eylül</span><br><span>2026</span></td>
  <td class="searchResultsLocationValue">İstanbul<br>Kadıköy</td>
</tr>
<tr class="nativeAd"><td><a href="/kampanya">Sponsorlu</a></td><td>999 TL</td></tr>
<tr class="searchResultsItem" data-id="1134567891">
  <td class="searchResultsTitleValue"><a class="classifiedTitle" href="/ilan/iphone-13-kilif-1134567891/detay">iPhone 13 Kılıf</a></td>
  <td class="searchResultsPriceValue">250 TL</td><td class="searchResultsDateValue">Bugün</td>
  <td class="searchResultsLocationValue">Ankara<br>Çankaya</td>
</tr>
</tbody></table>
"""

HASHED_HTML = """
<ul class="_1x2y">
  <li class="_9aB"><a href="/item/iphone-13-128-gb-temiz-iid-1234567890"><div class="_x1"><img src="/a.jpg">
     <span class="_p">₺31.000</span><span class="_t">iPhone 13 128 GB temiz</span>
     <div class="_l"><span>Kadıköy, İstanbul</span><span>Dün</span></div></div></a></li>
  <li class="_9aB"><a href="/item/ps5-disk-iid-1234567891"><div><img data-src="/b.jpg">
     <span>18.500 TL</span><span>PS5 Disk 2 kol</span><span>Çankaya, Ankara</span><span>3 gün önce</span></div></a></li>
  <li class="_9aB"><a href="/yardim">Yardım</a></li>
</ul>
"""

# letgo.com'un Eylül 2026 ızgara kartı yapısı (sadeleştirilmiş): bağlantı kartın kardeşi,
# kartta çok sayıda rozet var ("Öne Çıkan", "Elden al, kartla öde!", "6 taksit" ...).
LETGO_2026_HTML = """
<div data-testid="category-item-grid">
  <div data-testid="item-card" class="relative">
    <a href="/item/iphone-13-iid-1734422194" class="absolute inset-0"></a>
    <div><div data-slot="item-card">
      <div data-slot="item-card-image"><img src="https://imvm.letgo.com/a.jpg" alt="iPhone 13 128 GB Mavi">
        <div data-slot="item-card-image-bar"><span>Öne Çıkan</span></div></div>
      <div data-slot="item-card-body">
        <div><div class="flex">Elden al, kartla öde!</div></div>
        <div><p class="line-clamp-1">27.000 TL</p></div>
        <div class="overflow-hidden"><div class="line-clamp-1">iPhone 13 128 GB Mavi</div></div>
        <div><span>İstanbul, Beyoğlu</span></div>
      </div></div></div>
  </div>
  <div data-testid="item-card" class="relative">
    <a href="/item/ps5-disk-iid-1734422195" class="absolute inset-0"></a>
    <div><div data-slot="item-card">
      <div data-slot="item-card-image"><img src="https://imvm.letgo.com/b.jpg" alt=""></div>
      <div data-slot="item-card-body">
        <div>Cüzdanım</div><div>Güvende</div><div>Elden al, kartla öde!</div>
        <div><p class="line-clamp-1">18.500 TL</p><p>6 taksit</p></div>
        <div class="overflow-hidden"><div class="line-clamp-1">PS5 Disk 2 Kol</div></div>
        <div><span>4.6 Satıcı Puanı</span></div>
        <div><span>Ankara, Çankaya</span></div>
      </div></div></div>
  </div>
</div>
"""

DETAIL_HTML = """
<div class="classifiedDetailTitle"><h1>iPhone 13 128 GB Mavi</h1></div>
<div class="classifiedInfo"><h3>32.500 TL</h3>
<ul class="classifiedInfoList"><li><strong>İlan No</strong><span>1134567890</span></li>
<li><strong>Dahili Hafıza</strong><span>128 GB</span></li><li><strong>Garanti</strong><span>Hayır</span></li></ul></div>
<div id="classifiedDescription">Telefon temiz, iCloud kilidi yok. Kutusu ve faturası mevcut.</div>
"""


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pg = browser.new_page()
        yield pg
        browser.close()


def test_sahibinden_selectors(page):
    page.set_content(SAHIBINDEN_HTML)
    items = extract_cards(page, "sahibinden", default_sahibinden())
    assert [i.external_id for i in items] == ["1134567890", "1134567891"]
    first = items[0]
    assert first.title == "iPhone 13 128 GB Mavi" and first.price == 32500
    assert first.location == "İstanbul / Kadıköy" and first.date_text == "28 Eylül 2026"
    assert items[1].price == 250 and items[1].date_text == "Bugün"


def test_generic_link_based_cards(page):
    page.set_content(HASHED_HTML)
    items = extract_cards(page, "letgo", default_letgo())
    assert [i.external_id for i in items] == ["1234567890", "1234567891"]
    a, b = items
    assert a.price == 31000 and a.title == "iPhone 13 128 GB temiz"
    assert a.location == "Kadıköy, İstanbul" and a.date_text == "Dün"
    assert b.price == 18500 and b.title == "PS5 Disk 2 kol" and b.date_text == "3 gün önce"
    assert b.image_url.endswith("/b.jpg")


def test_parse_card_without_title_uses_longest_line():
    item = parse_card({"id": "9", "url": "u", "lines": ["₺5.000", "Samsung Galaxy S21 Ultra 256 GB", "Bugün"]}, "letgo")
    assert item and item.title == "Samsung Galaxy S21 Ultra 256 GB" and item.price == 5000


def test_detail_extraction(page):
    page.set_content(DETAIL_HTML)
    d = extract_details(page)
    assert d["price_value"] == 32500
    assert d["attributes"]["Dahili Hafıza"] == "128 GB"
    assert "iCloud kilidi yok" in d["description"]


def test_letgo_2026_cards_skip_badges(page):
    page.set_content(LETGO_2026_HTML)
    items = extract_cards(page, "letgo", default_letgo())
    assert [i.external_id for i in items] == ["1734422194", "1734422195"]
    a, b = items
    assert a.title == "iPhone 13 128 GB Mavi" and a.price == 27000 and a.location == "İstanbul, Beyoğlu"
    assert a.url.endswith("/item/iphone-13-iid-1734422194") and a.image_url.endswith("/a.jpg")
    # Fotoğraf alt metni boşsa gövdedeki başlık okunur; rozetler başlık/konum sanılmaz
    assert b.title == "PS5 Disk 2 Kol" and b.price == 18500 and b.location == "Ankara, Çankaya"


def test_letgo_search_url_sorts_newest_first():
    from autosell.automation.platforms.letgo import LetgoAdapter
    from autosell.config import Settings

    settings = Settings()
    adapter = LetgoAdapter(settings, None, None, None)  # type: ignore[arg-type]
    url = adapter.search_url(query="iphone 13")
    assert url == "https://www.letgo.com/arama?query_text=iphone+13&isSearchCall=true&sorting=desc-creation"


def test_badge_lines_are_not_titles():
    item = parse_card({"id": "7", "url": "u", "lines": ["Öne Çıkan", "Elden al, kartla öde!", "12.000 TL",
                                                        "iPhone 13", "İstanbul, Zeytinburnu"]}, "letgo")
    assert item and item.title == "iPhone 13" and item.location == "İstanbul, Zeytinburnu"
