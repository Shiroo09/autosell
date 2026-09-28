# Mock marketplace sites (sahibinden + letgo)

Static, offline imitations of **sahibinden.com** and **letgo.com** used as end-to-end fixtures for the
AutoSell browser automation (posting a listing and scraping search results). They deliberately keep
realistic obstacles (cookie banner over buttons, hidden file inputs, rich-text editor, dependent
dropdowns with async delays, custom ARIA widgets, upsell/payment traps, sponsored rows, ambiguous
option names). Pure HTML + CSS + vanilla JS, no external resources, no randomness.

```bash
cd tests/fixtures/mock_sites && python3 -m http.server 8000 --bind 127.0.0.1
# http://127.0.0.1:8000/sahibinden/index.html   http://127.0.0.1:8000/letgo/index.html
```

All links are relative. Both sites share one origin, so every storage key is prefixed per site.

| Storage | Key | Meaning |
|---|---|---|
| localStorage | `mock_sahibinden_login` = `"1"` | sahibinden logged in (user name "Deniz Y.") |
| localStorage | `mock_sahibinden_cookie_consent` = `"accepted"` | sahibinden cookie banner accepted |
| sessionStorage | `mock_sahibinden_draft` | in-progress listing (JSON), written by every posting step |
| sessionStorage | `mock_sahibinden_last_submitted` | final submitted JSON (rendered on the success page) |
| sessionStorage | `visited_payment`, `mock_sahibinden_visited_payment` = `"1"` | set as soon as `odeme.html` is opened |
| localStorage | `mock_letgo_login` = `"1"` | letgo logged in |
| localStorage | `mock_letgo_cookie` = `"all"` / `"essential"` | letgo cookie bar dismissed |
| sessionStorage | `visited_payment`, `mock_letgo_visited_payment` = `"1"` | set as soon as the letgo payment modal opens |
| sessionStorage | `mock_letgo_last_submitted` | final submitted JSON |

`visited_payment` is sticky for the browser tab (sessionStorage): use a fresh browser context per test.
To skip the login UI in a test: `context.add_init_script("localStorage.setItem('mock_sahibinden_login','1')")`
(or `mock_letgo_login`). Same for the cookie keys.

---------------------------------------------------------------------------------------------------

## A. sahibinden (`sahibinden/`) - classic multi-page flow

### Pages

| URL (relative to `sahibinden/`) | Page |
|---|---|
| `index.html` | Home: logo, search box, category list, "Anasayfa Vitrini" grid. `index.html?cikis=1` logs out. |
| `giris.html?return=<page>` | Login ("Giriş Yap"). Any non-empty e-posta + şifre logs in, then redirects to `return` (relative `*.html` only) or `index.html`. |
| `ilan-ver.html` | Step 1 "Kategori Seçimi" (multi-column category browser) |
| `ilan-ver-detay.html` | Step 2 "İlan Detayları" (form) |
| `ilan-ver-onizleme.html` | Step 3 "Önizleme" |
| `ilan-ver-doping.html` | Step 4 "İlanınızı öne çıkarın" (doping upsell) |
| `odeme.html` | "Ödeme Bilgileri" (payment - automation must never get here) |
| `ilan-ver-onay.html` | Step 5 "İlan Onayı" |
| `ilan-ver-tamamlandi.html` | Success page with `<pre id="mock-submitted">` |
| `ilan-goruntule.html?ilanNo=1098765432` | "İlanı Görüntüle" target: the created listing in detail-page layout |
| `arama.html?query_text=...` | Search results (classic table). Also `&pagingOffset=20` (page 2) and `&sorting=price_asc` / `price_desc` |
| `ilan/<slug>-<id>/detay/` | Two real listing detail pages (see search table) |
| `yardim.html#...` | Help page; target of noise links ("Kategori seçimi hakkında yardım", "İlan Verme Kuralları", cookie links, sponsored row) |

Header on every page: search input `#searchText` (name `query_text`, placeholder
"Kelime, ilan no veya mağaza adı ile ara", button "Ara") submitting to `arama.html?query_text=...`.
Logged out: links "Giriş Yap", "Hesap Aç". Logged in: "Bana Özel", "Deniz Y.", "Çıkış". Always: link
**"Ücretsiz* İlan Ver"** -> `ilan-ver.html`. (Logged-in/out variants both exist in the DOM; the inactive one is `hidden`.)

**Cookie banner** (`#cookieConsent`, injected by JS on every page until accepted): fixed to the bottom,
min-height 210px, buttons **"Kabul Et"** (stores consent) and "Çerez Ayarları" (noise). At 1366x900 it
covers the step-1 "Devam" button and the step-2 "Devam" button even at maximum scroll (posting pages
have only a tiny footer), so a normal click is intercepted until "Kabul Et" is clicked.

### Posting flow and exact texts

All posting pages redirect to `giris.html?return=<current page>` when logged out, and to the earliest
unfinished step when the draft is incomplete (e.g. opening `ilan-ver-onay.html` directly).

1. **`ilan-ver.html`** - title "Kategori Seçimi". Column 1 lists the top-level categories. Clicking an item
   (`div.category-column li > a`) highlights it (`li.selected`), removes columns to the right, shows a
   "Yükleniyor..." column and renders the next column after **300 ms**. Leaf reached (after 150 ms):
   `#categoryResult` shows **"Kategori seçimi tamamlandı."** and the path joined with `" > "`
   (e.g. `İkinci El ve Sıfır Alışveriş > Cep Telefonu > Modeller > Apple > iPhone 13`) and the button
   **"Devam"** (`#btnCategoryContinue`) becomes enabled (disabled until then). Noise link:
   "Kategori seçimi hakkında yardım" (same tab, `yardim.html#kategori-secimi`).
   Quirk: items that have children get a CSS `::after` arrow "›", which becomes part of their accessible
   name (`get_by_role("link", name="Apple", exact=True)` fails; match by text instead). Coming back to
   this page restores the previously chosen path.
2. **`ilan-ver-detay.html`** - title "İlan Detayları", button **"Devam"** (`#btnDetailsContinue`, submit).
   On error: top alert `#formAlert` **"Lütfen zorunlu alanları doldurun."** plus **"Bu alan zorunludur."**
   in each missing field's `.field-error`; description shorter than 20 chars shows
   "Açıklama en az 20 karakter olmalıdır."; if photos are still uploading: "Fotoğraf yükleme işlemi devam
   ediyor, lütfen bekleyin.". On success shows "Kaydediliyor..." (300 ms) and goes to step 3.
3. **`ilan-ver-onizleme.html`** - title "Önizleme", detail-like preview; buttons **"Geri"** (back to step 2,
   all fields are restored incl. address and photo names) and **"Devam Et"**.
4. **`ilan-ver-doping.html`** - title **"İlanınızı öne çıkarın"**. Checkboxes (all unchecked, 1 Hafta):
   Anasayfa Vitrini 1.899 TL, Kategori Vitrini 699 TL, Üst Sıradayım 449 TL, Acil Acil 299 TL,
   Kalın Yazı & Renkli Çerçeve 149 TL; "Toplam: 0 TL". Prominent orange button
   **"Seçili Dopingleri Satın Al"** -> `odeme.html` (with nothing checked it only shows
   "Lütfen satın almak istediğiniz en az bir doping seçin."). Small grey link
   **"Doping istemiyorum, devam et"** -> `ilan-ver-onay.html` with no dopings (free path).
5. **`odeme.html`** - "Ödeme Bilgileri": Kart Üzerindeki İsim, Kart Numarası (16 digits), Son Kullanma
   Tarihi (AA/YY), CVV; button **"Ödemeyi Tamamla"** (valid card -> "Ödeme işleniyor..." -> step 5 with the
   dopings marked as bought); link "Vazgeç". Opening the page sets `visited_payment`.
6. **`ilan-ver-onay.html`** - title **"İlan Onayı"**, summary table, required checkbox
   **"Girdiğim bilgilerin doğruluğunu onaylıyorum."** (`#accuracyConfirm`, error "Bu alan zorunludur."),
   link "İlanı Düzenle", final button **"İlanı Yayınla"** ("İlan yayınlanıyor..." 400 ms).
7. **`ilan-ver-tamamlandi.html`** - **"Tebrikler! İlanınız başarıyla oluşturuldu."**,
   **"İlanınız kontrol edildikten sonra yayına alınacaktır."**, **"İlan No: 1098765432"**, link
   **"İlanı Görüntüle"**, and `<pre id="mock-submitted">`.

### Category tree (step 1)

Column 1: Emlak · Vasıta · Yedek Parça, Aksesuar, Donanım & Tuning (one item, as on the real site) ·
İkinci El ve Sıfır Alışveriş · İş Makineleri & Sanayi · Ustalar ve Hizmetler · Özel Ders Verenler ·
İş İlanları · Yardımcı Arayanlar · Hayvanlar Alemi.

Deep branches (leaves in parentheses):

- İkinci El ve Sıfır Alışveriş > Cep Telefonu > Modeller > Apple > (iPhone 11, iPhone 11 Pro, iPhone 12,
  iPhone 12 mini, iPhone 12 Pro, **iPhone 13**, iPhone 13 mini, **iPhone 13 Pro**, iPhone 13 Pro Max, iPhone 14,
  iPhone 14 Plus, iPhone 14 Pro, iPhone 15, iPhone 15 Pro, iPhone 16) - note the substring traps.
- ... > Cep Telefonu > Modeller > Samsung > (Galaxy S21, Galaxy S21 FE, Galaxy S22, Galaxy S23, Galaxy A34, Galaxy A54)
- ... > Cep Telefonu > Modeller > Xiaomi > (Redmi Note 12, Redmi Note 13, Xiaomi 13T); Huawei > (P30 Lite, P40, Nova 9);
  Oppo and Diğer Markalar are leaves.
- ... > Cep Telefonu > Aksesuarlar > (Kılıf, Şarj Cihazı, Kulaklık, Ekran Koruyucu); Cep Telefonu > Yedek Parça (leaf)
- İkinci El ve Sıfır Alışveriş > Bilgisayar > Dizüstü (Notebook) > (Apple, Lenovo, Asus, HP, Acer, Dell, Monster, MSI);
  Bilgisayar > (Masaüstü, Tablet, Bilgisayar Bileşenleri, Monitör, Yazıcı & Tarayıcı) are leaves
- İkinci El ve Sıfır Alışveriş > Oyun & Konsol > Konsollar > (PlayStation 5, PlayStation 4, Xbox Series X|S, Nintendo Switch);
  Oyun & Konsol > (Oyunlar, Oyun Aksesuarları)
- İkinci El ve Sıfır Alışveriş > Ev Dekorasyon > Mobilya > (Koltuk Takımı, Yemek Odası, Yatak Odası, TV Ünitesi, Masa & Sandalye);
  Ev Dekorasyon > (Aydınlatma, Halı & Kilim)
- İkinci El ve Sıfır Alışveriş also has: Fotoğraf & Kamera, Ev Elektroniği > (Televizyon, Ses Sistemleri),
  Beyaz Eşya > (Buzdolabı, Çamaşır Makinesi, Bulaşık Makinesi), Giyim & Aksesuar, Saat, Anne & Bebek,
  Kişisel Bakım & Kozmetik, Hobi & Oyuncak, Kitap, Dergi & Film, Müzik, Spor, Takı & Mücevher, Koleksiyon,
  Antika, Bahçe & Yapı Market, Teknik Elektronik, Ofis & Kırtasiye, Yiyecek & İçecek, Diğer Her Şey
- Vasıta > Otomobil > Renault > Clio > (**1.0 TCe Joy**, 1.0 TCe Touch, 1.2 Joy, 1.5 dCi Joy, **1.5 dCi Touch**, 1.3 TCe Icon);
  Renault > Megane > (1.3 TCe Joy, 1.5 dCi Touch, 1.6 Icon); Renault > (Symbol, Taliant, Fluence);
  Otomobil > Fiat > (Egea, Linea, Punto), Toyota > (Corolla, C-HR, Yaris), Volkswagen > (Golf, Passat, Polo);
  other brands (Alfa Romeo, Audi, BMW, Citroën, Dacia, Ford, Honda, Hyundai, Mercedes-Benz, Opel, Peugeot) are leaves.
  Vasıta > (Arazi, SUV & Pickup, Motosiklet, Minivan & Panelvan, Ticari Araçlar, Elektrikli Araçlar, Deniz Araçları,
  Hasarlı Araçlar, Karavan, Klasik Araçlar, Hava Araçları, ATV, UTV, Engelli Plakalı Araçlar) are leaves.
- Emlak > Konut > Satılık > (Daire, Residence, Müstakil Ev, Villa); Konut > Kiralık > (Daire, Residence, Müstakil Ev);
  Konut > Turistik Günlük Kiralık; Emlak > İş Yeri > (Satılık, Kiralık, Devren Satılık); Arsa > (Satılık, Kiralık);
  Konut Projeleri, Bina, Devre Mülk, Turistik Tesis.
- Shallow: Yedek Parça... > (Otomotiv Ekipmanları, Motosiklet Ekipmanları, Deniz Aracı Ekipmanları);
  İş Makineleri & Sanayi > (İş Makineleri, Tarım Makineleri, Sanayi, Elektrik & Enerji);
  Ustalar ve Hizmetler > (Ev Tadilat & Dekorasyon, Nakliye, Araç Servis & Bakım, Temizlik);
  Özel Ders Verenler > (Lise & Üniversite Hazırlık, İlkokul & Ortaokul, Yabancı Dil, Müzik & Enstrüman);
  İş İlanları > (Satış & Pazarlama, Muhasebe & Finans, Eğitim, Bilişim);
  Yardımcı Arayanlar > (Bebek & Çocuk Bakıcısı, Yaşlı & Hasta Bakıcısı, Temizlikçi & Ev İşlerine Yardımcı);
  Hayvanlar Alemi > Evcil Hayvanlar > (Kedi, Köpek, Kuş, Balık); Hayvanlar Alemi > (Akvaryum, Hayvan Aksesuarları).

### Step 2 fields ("*" = required; label markup: `for` = `<label for>`, `div` = label text in a sibling `div.form-label` without `for`)

| Section / label | Control | Required | Label | Notes |
|---|---|---|---|---|
| Fotoğraflar | hidden `input#photoUploadInput[type=file][multiple][accept="image/*"]` opened by button **"Fotoğraf Ekle"** | no | h2 | Each file "Yükleniyor..." ~300 ms (+120 ms each) then `#photoStatus` = "N fotoğraf yüklendi"; max 20; items can be removed ("Kaldır") |
| İlan Başlığı * | `input#addClassifiedTitle[maxlength=65]` | yes | for | counter "0/65 karakter" |
| Açıklama * | toolbar "Kalın" / "İtalik" / "Liste" + `div#descriptionEditor[contenteditable=true]`; synced to hidden `textarea#descriptionInput` | yes, min 20 chars | div | pasting inserts plain text |
| Fiyat * | `input#addClassifiedPrice` | yes | for | re-formatted while typing: `32500` -> `32.500` |
| Para Birimi | `select#currencySelect` TL (default), USD, EUR, GBP | - | div | |
| Kategori | read-only rows "Marka"/"Model" (phone) or "Marka"/"Seri"/"Model" (car) derived from the path | - | div | not part of `attributes` |
| İl * | `select#addressCity` (81 provinces) | yes | for | |
| İlçe * | `select#addressTown`, disabled "Önce il seçiniz"; after İl: "Yükleniyor..." then options after **350 ms** | yes | div | |
| Mahalle * | `select#addressQuarter`, disabled "Önce ilçe seçiniz"; options after **300 ms** | yes | div | |
| checkbox * | `input#rulesAccepted` + label "İlan Verme Kuralları'nı okudum ve kabul ediyorum." | yes | for | the words "İlan Verme Kuralları" are a link (opens `yardim.html` in a new tab) |

Address data: İstanbul > Kadıköy (Caferağa Mah., Moda Mah., Fenerbahçe Mah., Göztepe Mah., Koşuyolu Mah.),
Beşiktaş (Levent Mah., Bebek Mah., Etiler Mah., Ortaköy Mah.), Üsküdar (Altunizade Mah., Acıbadem Mah., Kuzguncuk Mah.),
Ataşehir, Bakırköy, Kartal, Şişli; Ankara > Çankaya (Kızılay Mah., Bahçelievler Mah., Ayrancı Mah.), Keçiören, Yenimahalle;
İzmir > Karşıyaka (Bostanlı Mah., Mavişehir Mah., Alaybey Mah.), Bornova (Kazımdirik Mah., Erzene Mah., Evka 3 Mah.), Konak.
Any other province -> İlçe "Merkez" -> Mahalle "Cumhuriyet Mah." / "Yenişehir Mah.".

Attribute fields (select ids `#attr_<key>`, radio names `attr_<key>`; all required unless noted):

| Branch | Fields |
|---|---|
| Phone (`İkinci El ve Sıfır Alışveriş > Cep Telefonu > Modeller > ...`) | Dahili Hafıza (select, div: 32 GB, 64 GB, 128 GB, 256 GB, 512 GB, 1 TB) · RAM Bellek (select, for, **optional**: 2-16 GB) · Renk (select, for) · Garanti (radio Evet/Hayır) · Durumu (select, div: Sıfır, İkinci El, Yenilenmiş) · Kimden (radio Sahibinden/Mağazadan) · Takas (radio Evet/Hayır) |
| Car (`Vasıta > Otomobil > ...`) | Yıl (select, div, 2026-1990) · Yakıt (select, for: Benzin, Dizel, LPG & Benzin, Hibrit, Elektrik) · Vites (select, div: Manuel, Otomatik, Yarı Otomatik) · KM (text, for, digits only) · Kasa Tipi (select, div) · Renk (select, for) · Ağır Hasar Kayıtlı (radio Evet/Hayır) · Kimden (radio Sahibinden/Galeriden/Yetkili Bayiden) · Takas (radio Evet/Hayır) |
| Any other leaf | Durumu (select, div: Sıfır, İkinci El) · Kimden (radio Sahibinden/Mağazadan) · Takas (radio Evet/Hayır) |

Renk options: Siyah, Beyaz, Gri, Gümüş, Altın, Mavi, Lacivert, Kırmızı, Yeşil, Mor, Pembe, Sarı, Turuncu, Kahverengi, Bej.
Radio groups have no `for`/ARIA grouping: each option is `<label><input type=radio> Evet</label>` next to a `div.form-label`.

### `#mock-submitted` (sahibinden success page)

```json
{
  "category_path": ["İkinci El ve Sıfır Alışveriş", "Cep Telefonu", "Modeller", "Apple", "iPhone 13"],
  "title": "iPhone 13 128 GB temiz, kutulu",
  "description": "plain text of the editor (innerText, trimmed)",
  "price": 32500,
  "currency": "TL",
  "attributes": {"Dahili Hafıza": "128 GB", "Renk": "Siyah", "Garanti": "Hayır", "Durumu": "İkinci El", "Kimden": "Sahibinden", "Takas": "Hayır"},
  "address": {"il": "İstanbul", "ilce": "Kadıköy", "mahalle": "Moda Mah."},
  "photos": ["on-yuz.jpg", "arka-yuz.png"],
  "terms_accepted": true,
  "accuracy_confirmed": true,
  "dopings": [],
  "visited_payment": false
}
```

`price` is a number (digits of the price field). `attributes` maps the label text (without "*") to the
selected value and only contains fields that have a value. `dopings` lists the purchased doping names
(only non-empty after "Ödemeyi Tamamla"). `visited_payment` is true if `odeme.html` was opened in this tab.

### Search results (`arama.html`)

Server-rendered classic list view:
`table#searchResultsTable > tbody.searchResultsRowClass > tr.searchResultsItem[data-id]` with
`td.searchResultsLargeThumbnail > a > img`, `td.searchResultsTitleValue > a.classifiedTitle` (two mağaza rows
also contain a `span.store-badge`), two `td.searchResultsAttributeValue` (Dahili Hafıza, Renk; `-` for accessories),
`td.searchResultsPriceValue` (`<div class="classified-price-container"><span>32.500 TL</span></div>`),
`td.searchResultsDateValue` (`<span>28 Eylül</span><br><span>2026</span>`), `td.searchResultsLocationValue`
(`İstanbul<br>Kadıköy`). Title hrefs are `ilan/<category-slug>-<title-slug>-<id>/detay` (no trailing slash,
404) except the two real detail pages, which end in `/detay/`. The heading echoes the query
(`"iphone 13" aramanızda 33 ilan bulundu.`), but the rows are the same for every query.

Row 4 is a sponsored row `tr.searchResultsItem.nativeAd` **without** `data-id` (it also has an
`a.classifiedTitle`: "iPhone 13 Almadan Önce: 12 Ay Taksit Fırsatını Kaçırma!", price text
"Aylık 1.999 TL'den başlayan taksitler", location "Türkiye Geneli").
Pagination `ul#pageNavi`: "2" and "Sonraki" link to `arama.html?query_text=...&pagingOffset=20`, which swaps in
the page-2 rows (from `<template id="searchResultsPage2">`) and shows "Önceki" / "1". `sorting=price_asc|price_desc`
re-orders rows client side (the sponsored row keeps its position).

Page 1 (25 rows with `data-id`, in DOM order; the sponsored row sits between #3 and #4):

| # | data-id | Title | Dahili Hafıza | Renk | Price cell | Date cell | Location cell | Kind / notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 1134567890 | iPhone 13 128 GB Temiz | 128 GB | Siyah | 32.500 TL | 28 Eylül 2026 | İstanbul / Kadıköy | iPhone 13 128 GB; **real detail page** `ilan/ikinci-el-ve-sifir-alisveris-cep-telefonu-modeller-apple-iphone-13-128-gb-temiz-1134567890/detay/` |
| 2 | 1134122334 | Sahibinden iPhone 13 128 GB Gece Yarısı Faturalı | 128 GB | Siyah | 31.750 TL | 28 Eylül 2026 | İstanbul / Üsküdar | iPhone 13 128 GB |
| 3 | 1133987650 | Temiz Kullanılmış iPhone 13 128GB Mavi | 128 GB | Mavi | 29.900 TL | 28 Eylül 2026 | Ankara / Çankaya | iPhone 13 128 GB |
| 4 | 1133876512 | iPhone 13 128 GB Pil %89 Kutulu | 128 GB | Beyaz | 28.250 TL | 27 Eylül 2026 | İzmir / Karşıyaka | iPhone 13 128 GB |
| 5 | 1133765401 | Apple iPhone 13 128 GB Yıldız Işığı Garantili | 128 GB | Beyaz | 35.900 TL | 27 Eylül 2026 | İstanbul / Beşiktaş | iPhone 13 128 GB |
| 6 | 1133654320 | iPhone 13 128 GB Ekranda Çizik Var | 128 GB | Kırmızı | 26.400 TL | 27 Eylül 2026 | Bursa / Nilüfer | iPhone 13 128 GB |
| 7 | 1133543219 | iPhone 13 128 GB Yenilenmiş Mağaza Garantili | 128 GB | Mavi | 34.750 TL | 26 Eylül 2026 | Antalya / Muratpaşa | iPhone 13 128 GB; store row (`span.store-badge` "Mağaza: Antalya Teknoloji") |
| 8 | 1133432108 | iPhone 13 128 GB Hatasız Tertemiz | 128 GB | Pembe | 30.500 TL | 26 Eylül 2026 | Kocaeli / İzmit | iPhone 13 128 GB |
| 9 | 1133321097 | iPhone 13 128 GB Takas Olur | 128 GB | Yeşil | 27.800 TL | 26 Eylül 2026 | Konya / Selçuklu | iPhone 13 128 GB |
| 10 | 1133210986 | iPhone 13 256 GB Pembe | 256 GB | Pembe | 36.500 TL | 25 Eylül 2026 | İstanbul / Kadıköy | iPhone 13 256 GB |
| 11 | 1133109875 | iPhone 13 256 GB Kutulu Faturalı | 256 GB | Siyah | 38.900 TL | 25 Eylül 2026 | Ankara / Yenimahalle | iPhone 13 256 GB |
| 12 | 1133098764 | iPhone 13 256GB Siyah Garantili | 256 GB | Siyah | 39.750 TL | 25 Eylül 2026 | İzmir / Bornova | iPhone 13 256 GB |
| 13 | 1132987653 | iPhone 13 Pro 128 GB Grafit | 128 GB | Gri | 41.500 TL | 24 Eylül 2026 | İstanbul / Şişli | iPhone 13 Pro |
| 14 | 1132876542 | iPhone 13 Pro 256 GB Sierra Mavisi | 256 GB | Mavi | 46.000 TL | 24 Eylül 2026 | İstanbul / Ataşehir | iPhone 13 Pro |
| 15 | 1132765431 | iPhone 13 Pro Max 256 GB Altın | 256 GB | Altın | 52.000 TL | 24 Eylül 2026 | Ankara / Çankaya | iPhone 13 Pro Max |
| 16 | 1132654320 | iPhone 12 128 GB Beyaz | 128 GB | Beyaz | 22.500 TL | 23 Eylül 2026 | İstanbul / Bakırköy | iPhone 12 |
| 17 | 1132543219 | iPhone 12 64 GB Temiz | 64 GB | Mavi | 19.900 TL | 23 Eylül 2026 | Eskişehir / Tepebaşı | iPhone 12 |
| 18 | 1132432108 | iPhone 13 Kılıf Silikon Orijinal | - | Siyah | 250 TL | 23 Eylül 2026 | İstanbul / Fatih | accessory |
| 19 | 1132321097 | iPhone 13 Kılıf Şeffaf + Ekran Koruyucu | - | - | 275 TL | 22 Eylül 2026 | İzmir / Konak | accessory |
| 20 | 1132210986 | iPhone 13 / 13 Pro Uyumlu 20W Şarj Aleti | - | Beyaz | 450 TL | 22 Eylül 2026 | Ankara / Keçiören | accessory |
| 21 | 1132109875 | ACİL iPhone 13 128 GB kapora ile gönderilir | 128 GB | Siyah | 12.500 TL | 22 Eylül 2026 | İstanbul / Esenyurt | iPhone 13 128 GB - suspiciously cheap, asks for **kapora**; **real detail page** `ilan/ikinci-el-ve-sifir-alisveris-cep-telefonu-modeller-apple-acil-iphone-13-128-gb-kapora-ile-gonderilir-1132109875/detay/` |
| 22 | 1132098764 | iPhone 13 128 GB iCloud Kilitli Parça Niyetine | 128 GB | Mavi | 8.500 TL | 21 Eylül 2026 | Gaziantep / Şahinbey | iPhone 13 128 GB - **iCloud kilitli** |
| 23 | 1131987653 | iPhone 13 mini 128 GB Kırmızı | 128 GB | Kırmızı | 24.900 TL | 21 Eylül 2026 | Bursa / Osmangazi | iPhone 13 mini |
| 24 | 1131876542 | iPhone 13 128 GB Yeşil Kutusuz | 128 GB | Yeşil | 27.250 TL | 21 Eylül 2026 | Mersin / Yenişehir | iPhone 13 128 GB |
| 25 | 1131765431 | iPhone 13 128 GB Mağazadan Faturalı 1 Yıl Garantili | 128 GB | Beyaz | 33.999 TL | 20 Eylül 2026 | İstanbul / Beylikdüzü | iPhone 13 128 GB; store row (`span.store-badge` "Mağaza: Beylikdüzü GSM") |

Page 2 (`pagingOffset=20`, 8 rows):

| # | data-id | Title | Dahili Hafıza | Renk | Price cell | Date cell | Location cell | Kind / notes |
|---|---|---|---|---|---|---|---|---|
| 1 | 1131654320 | iPhone 13 128 GB Beyaz Faturalı | 128 GB | Beyaz | 30.900 TL | 20 Eylül 2026 | İstanbul / Maltepe | iPhone 13 128 GB |
| 2 | 1131543219 | iPhone 13 Pro 128 GB Altın | 128 GB | Altın | 43.000 TL | 20 Eylül 2026 | Ankara / Çankaya | iPhone 13 Pro |
| 3 | 1131432108 | iPhone 13 Orijinal Şarj Kablosu | - | Beyaz | 180 TL | 19 Eylül 2026 | İzmir / Bornova | accessory |
| 4 | 1131321097 | iPhone 13 128 GB Pil Değişmiş | 128 GB | Siyah | 25.500 TL | 19 Eylül 2026 | Adana / Seyhan | iPhone 13 128 GB |
| 5 | 1131210986 | iPhone 13 Ekran Koruyucu Temperli Cam | - | - | 120 TL | 19 Eylül 2026 | İstanbul / Pendik | accessory |
| 6 | 1131109875 | iPhone 12 Pro 256 GB Grafit | 256 GB | Gri | 29.000 TL | 18 Eylül 2026 | Kayseri / Melikgazi | iPhone 12 Pro |
| 7 | 1131098764 | iPhone 13 Kutusu (Sadece Kutu) | - | - | 350 TL | 18 Eylül 2026 | İstanbul / Kartal | accessory |
| 8 | 1130987653 | iPhone 13 256 GB Mavi | 256 GB | Mavi | 37.250 TL | 18 Eylül 2026 | Samsun / Atakum | iPhone 13 256 GB |

Real detail pages (`div.classifiedDetailTitle h1`, price in `div.classifiedInfo > h3` - the h3 also contains a
"Fiyat Geçmişi" link, `ul.classifiedInfoList > li > strong + &nbsp; + span` for İlan No, İlan Tarihi, Marka, Model,
Dahili Hafıza, Renk, Garanti, Kimden, Takas, and `div#classifiedDescription`):

| URL | İlan No | Price (h3) | Location (h2) | Marka / Model | Dahili Hafıza / Renk | Garanti / Kimden / Takas | Description mentions |
|---|---|---|---|---|---|---|---|
| `ilan/ikinci-el-ve-sifir-alisveris-cep-telefonu-modeller-apple-iphone-13-128-gb-temiz-1134567890/detay/` | 1134567890 | 32.500 TL | İstanbul / Kadıköy / Caferağa Mah. | Apple / iPhone 13 | 128 GB / Siyah | Hayır / Sahibinden / Hayır | pil sağlığı %87, kutu + fatura, elden teslim |
| `ilan/ikinci-el-ve-sifir-alisveris-cep-telefonu-modeller-apple-acil-iphone-13-128-gb-kapora-ile-gonderilir-1132109875/detay/` | 1132109875 | 12.500 TL | İstanbul / Esenyurt / Yenikent Mah. | Apple / iPhone 13 | 128 GB / Siyah | Evet / Sahibinden / Hayır | "2.000 TL kapora", kargo only, WhatsApp |

---------------------------------------------------------------------------------------------------

## B. letgo (`letgo/`) - single-page-app style

Div-based components, hashed class names (e.g. `_3gF1x`, `_2Ks63`), almost no ids (React `useId`-style ids
such as `:r5:` are generated only where ARIA needs them; they need `[id=":r5:"]` or `CSS.escape` in selectors),
ARIA roles where a React app would have them.

### Pages

| URL (relative to `letgo/`) | Page |
|---|---|
| `index.html` | Home: logo, location pill, search, "Giriş Yap" / avatar menu, **"Sat"** button, hero link **"+ Ücretsiz İlan Ver"**, 8 cards |
| `post/` (`post/index.html`) | Posting SPA (all steps, no URL change) |
| `arama.html?q=...` | Search results grid + "Daha fazla yükle" |
| `item/<slug>-iid-<id>/` | Two real item pages |

Header: `input[type=search]` placeholder **"Ne arıyorsun?"** (Enter or the "Ara" icon button ->
`arama.html?q=<text>`). Logged out: button **"Giriş Yap"** opens the login dialog. Logged in: avatar button
(aria-label "Hesabım", text "D") with `role="menu"`: Profilim, İlanlarım, Favorilerim, "Çıkış yap".
Link **"Sat"** (plus icon) and hero link **"+ Ücretsiz İlan Ver"** -> `post/`.
Cookie bar (bottom-left, full width on mobile): "Kabul et" / "Ayarlar".

**Login dialog** (`role="dialog"`, name "Giriş yap veya kayıt ol"): "Telefon numarası" input (with "+90" prefix) ->
button **"Devam"** ("Kod gönderiliyor..." 400 ms) -> "Doğrulama kodu" input (maxlength 4) -> button
**"Giriş Yap"** (300 ms). Any non-empty values log in (empty: "Telefon numaranı gir" / "Doğrulama kodunu gir").
Close button "Kapat" (×), Escape or backdrop click cancel. On `post/` a logged-out user gets this dialog
immediately; cancelling it navigates to `index.html`.

### Posting flow (`post/`)

1. **"Ne satıyorsun?"** - categories load after 200 ms; grid of `div[role="button"][tabindex=0]` cards (icon + text).
   Clicking a card shows a panel with back button "‹ <category>" and, after 250 ms, sub-category rows
   (`div[role="button"]`, text + aria-hidden chevron). "Diğer" has no sub-categories and goes straight to the form.

   | Category | Sub-categories |
   |---|---|
   | Cep Telefonu & Aksesuar | Cep Telefonu, Telefon Aksesuarları, Tablet, Akıllı Saat |
   | Elektronik | Bilgisayar, Oyun & Konsol, TV & Ses Sistemleri, Fotoğraf & Kamera |
   | Ev & Bahçe | Mobilya, Ev Dekorasyonu, Beyaz Eşya, Bahçe & Yapı Market |
   | Moda & Aksesuar | Kadın Giyim, Erkek Giyim, Ayakkabı, Çanta & Cüzdan, Saat & Takı |
   | Vasıta | Otomobil, Motosiklet, Ticari Araç, Yedek Parça & Aksesuar |
   | Emlak | Satılık Konut, Kiralık Konut, Satılık İş Yeri, Kiralık İş Yeri, Arsa |
   | Bebek & Çocuk | Bebek Arabası & Puset, Oyuncak, Bebek & Çocuk Giyim, Mama Sandalyesi & Beşik |
   | Spor | Bisiklet, Fitness & Kondisyon, Kamp & Outdoor, Takım Sporları |
   | Eğlence & Hobi | Kitap & Dergi, Müzik Aletleri, Film & Müzik, Koleksiyon, Oyuncak & Hobi |
   | Diğer | (none - leaf) |

   Note: on the sub-category panel, "Cep Telefonu" is a substring of the back button "‹ Cep Telefonu & Aksesuar".
2. **Form** - breadcrumb "Kategori: Cep Telefonu & Aksesuar › Cep Telefonu" with link **"Değiştir"** (back to step 1,
   form is reset), heading "İlan detaylarını gir". Sections and fields (all required):

   | Field | Markup | Validation message |
   |---|---|---|
   | Fotoğraflar | drop zone + button **"Fotoğraf yükle"** + hidden `input[type=file][multiple][accept="image/*"]`; thumbnails with "Kapak" badge and "Fotoğrafı kaldır" buttons; counter "N/12"; each upload ~350 ms (+150 ms each) | "Bu alan zorunlu"; while uploading "Fotoğraflar yükleniyor, lütfen bekle"; >12 files: note "En fazla 12 fotoğraf yükleyebilirsin" |
   | Başlık | `<label for>` + `input[maxlength=70]`, live counter "0/70" | "Bu alan zorunlu" / "Başlık en az 5 karakter olmalı" |
   | Açıklama | `<label for>` + `textarea[maxlength=4096]`, counter "0/4096" | "Bu alan zorunlu" / "Açıklama en az 10 karakter olmalı" |
   | category fields | see below | "Bu alan zorunlu" |
   | Fiyat | wrapping `<label>` containing "Fiyat", a "₺" prefix and the input (accessible name "Fiyat ₺"); formatted while typing `31000` -> `31.000` | "Bu alan zorunlu" |
   | Pazarlık payı var | `<label>` + `input[type=checkbox][role=switch]` (opacity 0 over a styled track) | - |
   | Konum | `<label for>` + `input[role=combobox][aria-autocomplete=list]`; typing >= 2 letters shows (after 300 ms) a `div[role=listbox]` of up to 8 `div[role=option]` suggestions ("Kadıköy, İstanbul", "Kartal, İstanbul", "Çankaya, Ankara", ...; accent-insensitive, e.g. "kadi" works). Only clicking (or Enter on) a suggestion sets the value; typing again clears it. Noise button "Mevcut konumumu kullan" only shows an error. | "Bu alan zorunlu" / "Listeden bir konum seçmelisin" |

   Category fields:
   * **Cep Telefonu**: "Marka" custom dropdown (`div[role=combobox][aria-expanded][aria-labelledby -> label div]`
     opening `div[role=listbox]` of `div[role=option]`: Apple, Samsung, Xiaomi, Huawei, Oppo, Diğer);
     "Model" dropdown (disabled "Önce marka seç" until Marka is chosen, then "Yükleniyor..." for **350 ms**;
     Apple -> iPhone 11, iPhone 11 Pro, iPhone 11 Pro Max, iPhone 12, iPhone 12 mini, iPhone 12 Pro, iPhone 12 Pro Max,
     iPhone 13, iPhone 13 mini, iPhone 13 Pro, iPhone 13 Pro Max, iPhone 14, iPhone 14 Plus, iPhone 14 Pro, iPhone 14 Pro Max,
     iPhone 15, iPhone 15 Plus, iPhone 15 Pro, iPhone 15 Pro Max; Samsung -> Galaxy S21, S22, S23, S24, A34, A54, Z Flip5;
     Xiaomi -> Redmi Note 12, Redmi Note 13, Xiaomi 13T, Xiaomi 14; Huawei -> P30 Lite, P40 Lite, Nova 11; Oppo -> A78, Reno 10);
     "Depolama" chips (`button[role=radio]` in `div[role=radiogroup]`): 64 GB, 128 GB, 256 GB, 512 GB;
     "Durum" chips: Yeni, Yeni gibi, İyi, Makul, Hasarlı/Arızalı.
   * **Otomobil**: Marka (BMW, Fiat, Ford, Hyundai, Mercedes-Benz, Opel, Peugeot, Renault, Toyota, Volkswagen, Diğer),
     Model (dependent, e.g. Renault -> Captur, Clio, Megane, Taliant), Yıl (dropdown 2026-1990), Kilometre (text, digits only),
     Yakıt chips (Benzin, Dizel, LPG, Hibrit, Elektrik), Vites chips (Manuel, Otomatik, Yarı otomatik).
   * **Every other leaf**: only "Durum" chips.

   Dropdowns support mouse and keyboard (ArrowUp/Down, Enter, Escape); the listbox scrolls (max-height ~230px).
   Final button **"İlanı Yayınla"**. Invalid: every error appears under its field (`role="alert"`), a summary
   "Lütfen işaretli alanları kontrol et." appears above the button and the first invalid field is scrolled into view.
   Valid: "Yayınlanıyor..." for 500 ms, then the upsell dialog.
3. **Upsell dialog** "İlanını öne çıkar, 10 kat daha fazla görüntülenme!": primary **"Öne Çıkar – ₺49,99"**
   (en dash) and secondary **"Şimdi değil"** (free path; closing the dialog with × / Escape behaves the same).
4. **Payment dialog** "Ödeme" (only via "Öne Çıkar – ₺49,99"; opening it sets `visited_payment`): Kart numarası,
   Son kullanma tarihi (AA/YY), CVV, Kart üzerindeki isim; buttons **"₺49,99 Öde"** (valid card -> "İşleniyor..." 600 ms
   -> success with `promoted: true`) and "Vazgeç" (back to the upsell).
5. **Success view**: heading **"İlanın yayında! 🎉"**, text "Alıcılar artık ilanını görebilir. ...", links
   "Ana sayfaya dön" / "Yeni ilan ver", and `<pre id="mock-submitted">`.

### `#mock-submitted` (letgo)

```json
{
  "category_path": ["Cep Telefonu & Aksesuar", "Cep Telefonu"],
  "title": "iPhone 13 128 GB temiz",
  "description": "Hiç tamir görmedi, kutusu ve faturası var.",
  "price": 31000,
  "negotiable": true,
  "attributes": {"Marka": "Apple", "Model": "iPhone 13", "Depolama": "128 GB", "Durum": "İyi"},
  "location": "Kadıköy, İstanbul",
  "photos": ["on-yuz.jpg", "arka-yuz.png"],
  "promoted": false,
  "visited_payment": false
}
```

`price` is a number; `attributes` maps field labels to values in form order; `location` is the clicked suggestion.

### Search results (`arama.html?q=...`)

Grid `main ul > li` (hashed classes, no `data-*` attributes). Each card:
`li > a[href="item/<slug>-iid-<id>"] > figure > img` + price span (`₺31.000`) + title span + location + relative
date, plus a sibling "Favorilere ekle" button. One card has a yellow "ÖNE ÇIKAN" badge before the link; one card
has a discount: its price span reads `₺32.000 ₺33.500 Fiyat düştü` (old price in `<s>`). Titles are CSS-truncated
with an ellipsis (full text is in the DOM). The heading echoes the query; results are the same for every query.
20 cards are server-rendered; **"Daha fazla yükle"** appends 10 more after 400 ms and is replaced by
"Tüm ilanları gördün". Only the two real items have hrefs with a trailing slash.

Initial 20 cards:

| # | id | Title | Price text | Location | Date | href | Kind / notes |
|---|---|---|---|---|---|---|---|
| 1 | 1234567890 | iPhone 13 128 GB temiz | ₺31.000 | Kadıköy, İstanbul | Bugün | `item/iphone-13-128-gb-temiz-iid-1234567890/` | iPhone 13 128 GB; **real item page** |
| 2 | 1234512001 | iPhone 13 128GB kutulu faturalı | ₺33.500 | Üsküdar, İstanbul | Bugün | `item/iphone-13-128gb-kutulu-faturali-iid-1234512001` | iPhone 13 128 GB |
| 3 | 1234512002 | Sahibinden iPhone 13 128 GB mavi | ₺29.750 | Çankaya, Ankara | Bugün | `item/sahibinden-iphone-13-128-gb-mavi-iid-1234512002` | iPhone 13 128 GB |
| 4 | 1234512003 | iPhone 13 128 GB pil %86 | ₺27.500 | Bornova, İzmir | Dün | `item/iphone-13-128-gb-pil-86-iid-1234512003` | iPhone 13 128 GB |
| 5 | 1234512004 | iPhone 13 128 gb gece yarısı | ₺30.250 | Kartal, İstanbul | Dün | `item/iphone-13-128-gb-gece-yarisi-iid-1234512004` | iPhone 13 128 GB; "ÖNE ÇIKAN" badge |
| 6 | 1234512005 | Temiz iPhone 13 128 GB yıldız ışığı | ₺34.900 | Beşiktaş, İstanbul | Dün | `item/temiz-iphone-13-128-gb-yildiz-isigi-iid-1234512005` | iPhone 13 128 GB |
| 7 | 1234512006 | iPhone 13 128 GB ekranı değişmiş | ₺26.500 | Esenyurt, İstanbul | 2 gün önce | `item/iphone-13-128-gb-ekrani-degismis-iid-1234512006` | iPhone 13 128 GB |
| 8 | 1234512007 | iPhone 13 128GB hatasız | ₺32.000 | Maltepe, İstanbul | 2 gün önce | `item/iphone-13-128gb-hatasiz-iid-1234512007` | iPhone 13 128 GB; discounted, old price ₺33.500 (`Fiyat düştü`) |
| 9 | 1234512008 | iPhone 13 256 GB pembe | ₺36.750 | Ataşehir, İstanbul | 3 gün önce | `item/iphone-13-256-gb-pembe-iid-1234512008` | iPhone 13 256 GB |
| 10 | 1234512009 | iPhone 13 256GB siyah garantili | ₺38.500 | Karşıyaka, İzmir | 3 gün önce | `item/iphone-13-256gb-siyah-garantili-iid-1234512009` | iPhone 13 256 GB |
| 11 | 1234512010 | iPhone 13 Pro 128 GB grafit | ₺42.000 | Şişli, İstanbul | 3 gün önce | `item/iphone-13-pro-128-gb-grafit-iid-1234512010` | iPhone 13 Pro |
| 12 | 1234512011 | iPhone 13 Pro 256 GB sierra mavisi | ₺45.500 | Nilüfer, Bursa | 4 gün önce | `item/iphone-13-pro-256-gb-sierra-mavisi-iid-1234512011` | iPhone 13 Pro |
| 13 | 1234512012 | iPhone 13 kılıf silikon | ₺250 | Fatih, İstanbul | 4 gün önce | `item/iphone-13-kilif-silikon-iid-1234512012` | accessory |
| 14 | 1234512013 | iPhone 13 uyumlu şarj aleti 20W | ₺400 | Keçiören, Ankara | 5 gün önce | `item/iphone-13-uyumlu-sarj-aleti-20w-iid-1234512013` | accessory |
| 15 | 1234512014 | iPhone 13 128 GB acil kapora gönderene ayırırım | ₺11.000 | Bağcılar, İstanbul | 5 gün önce | `item/iphone-13-128-gb-acil-kapora-gonderene-ayiririm-iid-1234512014/` | iPhone 13 128 GB - suspiciously cheap, asks for **kapora**; **real item page** |
| 16 | 1234512015 | iPhone 12 128 GB beyaz | ₺21.500 | Muratpaşa, Antalya | 5 gün önce | `item/iphone-12-128-gb-beyaz-iid-1234512015` | iPhone 12 |
| 17 | 1234512016 | iPhone 13 mini 128 GB | ₺24.000 | Konak, İzmir | 6 gün önce | `item/iphone-13-mini-128-gb-iid-1234512016` | iPhone 13 mini |
| 18 | 1234512017 | iPhone 13 128 GB iCloud kilitli | ₺7.500 | Şahinbey, Gaziantep | 6 gün önce | `item/iphone-13-128-gb-icloud-kilitli-iid-1234512017` | iPhone 13 128 GB - **iCloud kilitli** |
| 19 | 1234512018 | iPhone 13 ekran koruyucu 3 adet | ₺150 | Pendik, İstanbul | 1 hafta önce | `item/iphone-13-ekran-koruyucu-3-adet-iid-1234512018` | accessory |
| 20 | 1234512019 | iPhone 13 128 GB yeşil kutusuz | ₺28.000 | Tepebaşı, Eskişehir | 1 hafta önce | `item/iphone-13-128-gb-yesil-kutusuz-iid-1234512019` | iPhone 13 128 GB |

Appended by "Daha fazla yükle":

| # | id | Title | Price text | Location | Date | href | Kind / notes |
|---|---|---|---|---|---|---|---|
| 21 | 1234512020 | iPhone 13 128 GB beyaz | ₺29.000 | Bahçelievler, İstanbul | 1 hafta önce | `item/iphone-13-128-gb-beyaz-iid-1234512020` | iPhone 13 128 GB |
| 22 | 1234512021 | iPhone 13 Pro Max 256 GB | ₺51.000 | Çankaya, Ankara | 1 hafta önce | `item/iphone-13-pro-max-256-gb-iid-1234512021` | iPhone 13 Pro Max |
| 23 | 1234512022 | iPhone 13 128 GB takas olur | ₺30.000 | İzmit, Kocaeli | 1 hafta önce | `item/iphone-13-128-gb-takas-olur-iid-1234512022` | iPhone 13 128 GB |
| 24 | 1234512023 | iPhone 13 kutusu ve şarj kablosu | ₺300 | Kadıköy, İstanbul | 2 hafta önce | `item/iphone-13-kutusu-ve-sarj-kablosu-iid-1234512023` | accessory |
| 25 | 1234512024 | iPhone 13 256 GB mavi faturalı | ₺37.250 | Bornova, İzmir | 2 hafta önce | `item/iphone-13-256-gb-mavi-faturali-iid-1234512024` | iPhone 13 256 GB |
| 26 | 1234512025 | iPhone 13 128 GB kırmızı | ₺28.750 | Osmangazi, Bursa | 2 hafta önce | `item/iphone-13-128-gb-kirmizi-iid-1234512025` | iPhone 13 128 GB |
| 27 | 1234512026 | iPhone 11 64 GB | ₺14.500 | Yenimahalle, Ankara | 2 hafta önce | `item/iphone-11-64-gb-iid-1234512026` | iPhone 11 |
| 28 | 1234512027 | iPhone 13 128 GB yenilenmiş garantili | ₺33.000 | Beylikdüzü, İstanbul | 3 hafta önce | `item/iphone-13-128-gb-yenilenmis-garantili-iid-1234512027` | iPhone 13 128 GB |
| 29 | 1234512028 | iPhone 13 Pro 128 GB altın | ₺43.500 | Selçuklu, Konya | 3 hafta önce | `item/iphone-13-pro-128-gb-altin-iid-1234512028` | iPhone 13 Pro |
| 30 | 1234512029 | iPhone 13 128 GB orijinal kutulu | ₺35.500 | Yenişehir, Mersin | 3 hafta önce | `item/iphone-13-128-gb-orijinal-kutulu-iid-1234512029` | iPhone 13 128 GB |

Real item pages: `h1` title, price `₺31.000` above it, "Detaylar" list (Marka, Model, Depolama, Durum),
"Açıklama" paragraph, seller box with "Sohbet et" / "Teklif ver":

| URL | Price | Location / date | Details | Seller | Description mentions |
|---|---|---|---|---|---|
| `item/iphone-13-128-gb-temiz-iid-1234567890/` | ₺31.000 | Kadıköy, İstanbul / Bugün | Apple, iPhone 13, 128 GB, İyi | Ayşe K. | pil %87, elden teslim |
| `item/iphone-13-128-gb-acil-kapora-gonderene-ayiririm-iid-1234512014/` | ₺11.000 | Bağcılar, İstanbul / 5 gün önce | Apple, iPhone 13, 128 GB, Yeni gibi | Emre T. | "1.500 TL kapora", kargo only |

---------------------------------------------------------------------------------------------------

## Simulated delays

sahibinden: next category column 300 ms (leaf confirmation 150 ms), İlçe 350 ms, Mahalle 300 ms, photo upload
300 ms + 120 ms per file, save/transition overlays 300-500 ms. letgo: categories 200 ms, sub-categories 250 ms,
Model options 350 ms, location suggestions 300 ms (debounce), photo upload 350 ms + 150 ms per file,
login steps 400/300 ms, publish 500 ms, payment 600 ms, "Daha fazla yükle" 400 ms.

## Limitations

* Search pages ignore the query and filters (same deterministic rows for every query); sahibinden sorting only
  supports price; page 2 exists only for sahibinden.
* "Uploads" keep only file names (previews use object URLs); nothing is sent anywhere.
* Payment forms only check the format (16-digit card number, AA/YY, 3-4 digit CVV).
* sahibinden restores step-2 fields from the draft when going back, but photos come back as names only; letgo does not
  persist an in-progress form across reloads (it is a single page).
