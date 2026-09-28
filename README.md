# AutoSell

**Sahibinden ve Letgo için yapay zekâ destekli ilan asistanı ve al-sat fırsat avcısı.**

Fotoğraflarını yükle ve birkaç satır not yaz; gerisini AutoSell hazırlar:

- **En iyi başlık:** Yapay zekâ her platform için 5 başlık adayı üretir. Yerel bir puanlayıcı karakter sınırı, arama kelimeleri ve kurallara uyuma bakarak en iyisini seçer.
- **İlgi çeken açıklama:** Açıklama düzenli, dürüst ve ikna edicidir. Telefon, link ve e-posta gibi kurallara aykırı içerik otomatik temizlenir.
- **Kategori ve özellikler:** Kategori yolu ve tüm ilan özellikleri (hafıza, renk, garanti, kimden, takas…) otomatik doldurulur. Formdaki seçenekler canlı okunur. Eşleşmeyen alanları yapay zekâ, yalnızca sitenin sunduğu seçenekler arasından seçer.
- **Otomatik ilan verme:** Kendi tarayıcı oturumunla Sahibinden ve Letgo'da ilan verir: kategori, form, fotoğraf, adres, önizleme. Doping ve öne çıkarma adımları ücretsiz geçilir.
- **Fırsat avcısı:** Takip listelerindeki yeni ilanları tarar ve emsal ilanlarla fiyat araştırması yapar. Tahmini kâr, marj ve risk puanıyla al-sat fırsatlarını bulur, istersen Telegram'dan bildirir.
- **Web paneli:** Mobil ve masaüstü uyumludur, telefonun ana ekranına eklenebilir (PWA) ve karanlık modu destekler.
- **Yapay zekâ sağlayıcısı:** OpenAI uyumlu her API desteklenir. Varsayılan olarak `betaapiv2.llmapi.art` üzerindeki **muse-spark-1.3** modeli kullanılır; OpenAI, OpenRouter, Groq, DeepSeek, yerel Ollama ve LM Studio da seçilebilir. İstenirse Claude (Anthropic) kullanılabilir.

> ⚠️ **Önemli:** Sahibinden ve Letgo'nun kullanım koşulları otomasyon araçlarını kısıtlayabilir. Araç yalnızca **kendi hesabınla, kendi ilanların için** tasarlandı ve sorumluluk kullanıcıya aittir.
>
> - Siteyi yormamak için yavaş, insan hızında çalışır.
> - CAPTCHA'yı atlatmaya ya da tarayıcı parmak izini gizlemeye çalışmaz. Giriş, SMS kodu ve CAPTCHA adımlarını sana bırakır.
> - **Hiçbir ödemeyi yapmaz.** Ödeme sayfası görünürse durur.
> - Varsayılan olarak son **"Yayınla"** düğmesinden önce senden onay ister.

---

## Kurulum

Gereksinim: **Python 3.10+**.

```bash
git clone https://github.com/Shiroo09/autosell.git
cd autosell
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -e .
playwright install chromium       # otomasyonun kullanacağı tarayıcı
```

İsteğe bağlı: iPhone HEIC fotoğrafları için `pip install pillow-heif`.

API anahtarını panelden girebilir ya da `.env` dosyasına yazabilirsin. `.env` git'e eklenmez:

```bash
cp .env.example .env      # Windows: copy .env.example .env
# .env içinde OPENAI_API_KEY=... satırını doldur
```

## Hızlı başlangıç

```bash
autosell panel            # http://127.0.0.1:8000 adresinde paneli açar
```

1. **Ayarlar → Yapay Zekâ:** OpenAI uyumlu sağlayıcı hazır gelir (`https://betaapiv2.llmapi.art/v1`, model `muse-spark-1.3`). API anahtarını gir ve "Bağlantıyı test et" ile dene. İstersen modeli listeden değiştir ya da Claude'a geç.
2. **Ayarlar → Satıcı Profili:** il, ilçe ve mahalleyi gir; ilan formundaki adres alanları buradan doldurulur. Takas, pazarlık ve teslimat tercihlerini de burada seç.
3. **Ayarlar → Platformlar → Giriş yap:** Açılan tarayıcı penceresinde Sahibinden ve Letgo hesaplarına bir kez giriş yap. Oturum `veri/tarayici/` altında saklanır.
4. **Yeni İlan:** Fotoğrafları yükle, kısa notunu ve fiyatı yaz, sonra **"✨ Yapay zekâ ile ilan oluştur"** düğmesine bas.
5. Taslağı kontrol et, gerekirse başlık adaylarından birini seç ya da düzenle.
6. **"Sahibinden'de yayınla" / "Letgo'da yayınla":** Tarayıcı formu doldurur ve son adımda panelden onay ister. Onayı panelden verebilir ya da tarayıcıda kendin "Yayınla"ya basabilirsin.

**Önce denemek istersen:** `autosell panel --demo`. API anahtarı gerekmez; örnek taslaklar, takip listeleri ve fırsatlarla açılır.

### Telefondan kullanım

Panel, AutoSell'in çalıştığı bilgisayarda açılır; telefonla aynı Wi-Fi'dan bağlanabilirsin:

```bash
# Önce Ayarlar → Panel Güvenliği'nden şifre belirle (ya da AUTOSELL_PANEL_PASSWORD tanımla)
autosell panel --host 0.0.0.0
```

Telefonda `http://<bilgisayarın-yerel-IP'si>:8000` adresini aç. Tarayıcı menüsünden **"Ana ekrana ekle"** diyerek uygulama gibi kullanabilirsin. Şifre tanımlanmadan panel ağa açılmaz.

**Uzaktan tarayıcı kontrolü:** Otomasyon giriş, SMS kodu, CAPTCHA ya da son onay için seni beklerken panelde **"📱 Tarayıcıyı buradan kontrol et"** düğmesi çıkar. Açılan pencerede tarayıcı ekranını canlı görür, dokunarak tıklar, yazı yazar ve Enter/Tab gibi tuşlara basarsın. Bilgisayarın başında olmana gerek kalmaz. Görünmez (headless) modda, örneğin bir sunucuda çalışırken de kullanılabilir.

---

## Nasıl çalışır?

### 1. İlan metni üretimi

Yapay zekâya fotoğraflar (varsayılan en fazla 6), satıcı notları, fiyat, satıcı profili ve her platformun kuralları gönderilir: başlık sınırı (Sahibinden 50, Letgo 70 karakter; ayarlanabilir) ve emoji izni. Model yapılandırılmış JSON döner (Claude structured outputs / OpenAI `json_schema`):

- ürün analizi (marka, model, durum, öne çıkanlar, kusurlar, kutu içeriği, anahtar kelimeler)
- **eksik bilgiler** (ör. "pil sağlığı yüzdesi"): panelde öneri olarak gösterilir
- **uyarılar** (yasaklı veya kayıt dışı ürün şüphesi vb.)
- en iyi kapak fotoğrafı
- platform başına kategori yolu, 5 başlık adayı, açıklama ve özellik listesi

**Başlık puanlayıcı** (`listing/title.py`):

- Uzunluğun sınırın %70-100'ünü kullanmasını, marka/modelin başta olmasını, anahtar kelime kapsamını ve güven sinyallerini (garantili, kutulu, faturalı…) ödüllendirir.
- İletişim bilgisini, emojiyi, aşırı büyük harf ve noktalamayı, kelime tekrarını (keyword stuffing) cezalandırır.
- Sınırı aşan adaylar kelime bölünmeden kısaltılır.

### 2. İlan verme (tarayıcı otomasyonu)

Sitelerin HTML yapısı sık değiştiği için AutoSell sabit CSS seçicilerine bağlı değildir:

1. Her adımda sayfanın **anlık görüntüsü** alınır: form alanları etiketleriyle, tıklanabilir öğeler metinleriyle.
2. Sayfa sınıflandırılır: giriş, CAPTCHA, SMS kodu, kategori seçimi, ilan formu, doping, önizleme/onay, başarı.
3. **Kategori:** Yapay zekânın önerdiği yol sitede adım adım bulunur. Tıklamadan sonra beliren yeni seçenekler alt kategori kabul edilir. Eşleşme yoksa yapay zekâ mevcut seçeneklerden birini seçer.
4. **Form:** Alanlar etiketlerine göre tanınır: başlık, açıklama (zengin metin editörleri dahil), fiyat, para birimi, İl→İlçe→Mahalle, konum otomatik tamamlama, fotoğraf yükleme, kurallar onay kutusu. Bağımlı alanlar (Marka→Model) için birkaç tur yapılır. Eşleşmeyen alanlar tek bir yapay zekâ çağrısıyla yalnızca sitenin sunduğu seçeneklerden doldurulur.
5. Sezgisel yöntemler takılırsa **yapay zekâ adım ajanı** sayfayı okuyup tek tek eylem seçer. Ödeme veya öne çıkarma satın alma, hassas alana yazma ve (onaylı modda) son "Yayınla" düğmesi kod seviyesinde engellenir.
6. Hiçbiri olmazsa işlem **sana devredilir**: panelde bir uyarı çıkar, sen tarayıcıda adımı tamamlayınca otomasyon devam eder.

İlk kullanımda onaylı modda (varsayılan) ilerleyip tarayıcıyı izlemen önerilir. Her şey yolundaysa **Ayarlar → Platformlar → Otomatik yayınla** açılabilir.

### 3. Fırsat avcısı (al-sat)

1. **Takip listesi ekle:** arama kelimesi ya da sitede filtreleyip (kategori, şehir, fiyat, "sahibinden") kopyaladığın **arama bağlantısı**. En güvenilir yol bağlantıyı yapıştırmaktır.
2. Zamanlayıcı her listeyi ayarlanan aralıkla (varsayılan 15 dk, en az 5 dk) tarar ve ilanları veritabanına kaydeder. **Fiyat düşüşleri** de izlenir.
3. Her yeni ya da ucuzlayan ilan için **emsal ilanlardan piyasa değeri** hesaplanır:
   - Başlıklar karşılaştırılır; kapasite (128 GB ≠ 256 GB), sürüm (Pro/Max/Plus), model numarası ve aksesuar/parça farkları elenir.
   - Aykırı fiyatlar IQR ile atılır.
   - Benzerlik ağırlıklı medyan ve yüzdelikler bulunur.
4. **Kâr hesabı** (`market/deals.py`):

   ```
   alış   = ilan fiyatı × (1 − pazarlık %)
   satış  = emsallerin %45'lik dilimi × (1 − komisyon %) − sabit masraf
   kâr    = satış − alış          marj = kâr / alış
   ```

5. **Puan (0-100):** marj, kâr büyüklüğü, emsal güveni, ilanın yeniliği ve fiyat düşüşü artırır; riskler düşürür. Riskler ilan metninden otomatik algılanır:
   - kapora/ön ödeme
   - iCloud veya hesap kilidi
   - kayıt dışı/yurt dışı cihaz (IMEI)
   - replika
   - arıza/hasar, ağır hasar, değişen/boya
   - "piyasanın yarısının altında" fiyat

   "Değişensiz", "hasar kaydı yok" gibi olumsuz kalıplar risk sayılmaz.
6. En iyi adayların detay sayfası açılır ve açıklamadaki riskler de değerlendirilir. İsteğe bağlı olarak **yapay zekâ** ilanı tüccar gözüyle yorumlar: gerçekten aynı ürün mü, riskler, pazarlık teklifi. Claude ile istenirse **web araması** yaparak güncel sıfır ve ikinci el fiyatları da kontrol eder.
7. Eşiği geçen fırsatlar panelde listelenir, ayarlandıysa **Telegram**'dan bildirilir.

**Fiyat araştırması:** Kendi ilanın için "Fiyat araştır" düğmesi ya da **Fiyat Araştırması** ekranı benzer ilanları tarar. Hızlı satış, piyasa ve üst fiyat önerileriyle birlikte fiyat dağılımını gösterir.

---

## Yapay zekâ sağlayıcıları

| Sağlayıcı | Ayar | Not |
|---|---|---|
| **OpenAI uyumlu** (varsayılan) | Base URL `https://betaapiv2.llmapi.art/v1`, model `muse-spark-1.3` | Resmi `openai` SDK'sı. OpenAI, OpenRouter (`https://openrouter.ai/api/v1`), Groq, DeepSeek, Ollama (`http://localhost:11434/v1`), LM Studio (`http://localhost:1234/v1`) de kullanılabilir. Sunucu `json_schema`'yı desteklemiyorsa `json_object`'e, o da yoksa serbest metinden JSON ayıklamaya düşer. Görsel desteklemeyen modellerde fotoğraflar otomatik çıkarılır. Model adı sunucudaki kimlikle birebir değilse ("muse spark 1.3" gibi) sunucunun model listesinden en yakın olan seçilir. Adres `/v1` ile bitmiyorsa bir kez `/v1` eklenerek denenir. Anahtar: panel ya da `OPENAI_API_KEY`. |
| **Claude** | Model `claude-opus-5-5`, efor `high` | Resmi `anthropic` SDK'sı; yapılandırılmış çıktı, görsel analiz, web araştırması. Güvenlik sınıflandırıcısı reddederse Anthropic'in önerdiği modelle sunucu tarafında yeniden dener (`fallbacks: "default"`; Ayarlar'dan kapatılabilir). Anahtar: panel ya da `ANTHROPIC_API_KEY`. |

Yerel ve küçük modellerde başlık/açıklama kalitesi düşebilir. Görsel analiz için görsel destekli bir model (ör. `llama3.2-vision`, `qwen2.5-vl`) seç.

## Komut satırı

```bash
autosell panel [--host 0.0.0.0] [--port 8000] [--demo]
autosell giris sahibinden|letgo                    # oturum açıp kaydet
autosell olustur ./urun-klasoru --fiyat 32500      # fotoğraf + notlar.txt → taslak
autosell yayinla <taslak-id> [--platform letgo] [--otomatik]
autosell toplu ./urunler [--platform sahibinden,letgo] [--sadece-olustur] [--otomatik]
autosell tara [--izle]                             # takip listelerini tara (sürekli)
autosell arastir "iPhone 13 128 GB" --platform sahibinden
autosell ayarlar                                   # ayar dosyasının yeri ve içeriği
```

**Toplu mod klasör yapısı:** her ürün ayrı bir alt klasördür.

```
urunler/
  iphone13/
    1.jpg  2.jpg  3.jpg
    notlar.txt        # ilk satırlardan birine "fiyat: 32500" yazılabilir
  ps5/
    kapak.jpg
    notlar.txt
```

## Ayarlar ve veri

- Tüm veriler `./veri` klasöründedir. Değiştirmek için `--veri` parametresini ya da `AUTOSELL_DATA_DIR` ortam değişkenini kullan.
  - `ayarlar.json`: ayarlar; panelden düzenlenir, API anahtarları burada saklanır, dosya yalnız senin kullanıcına açıktır
  - `autosell.db`: taslaklar, takip listeleri, piyasa ilanları, fiyat geçmişi, fırsatlar (SQLite)
  - `ilanlar/<id>/`: yüklenen fotoğraflar (EXIF ve GPS bilgisi silinerek kaydedilir)
  - `tarayici/<platform>/`: tarayıcı oturumları. **Bu klasörü kimseyle paylaşma.**
  - `ekran/`: yayın öncesi/sonrası ve hata ekran görüntüleri
- Ortam değişkenleri (`.env` dosyası da okunur):
  - Gizli alanlar: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `AUTOSELL_PANEL_PASSWORD`. Ayar dosyasında boş bırakılan gizli alanlar bunlardan okunur.
  - Varsayılanlar: `AUTOSELL_AI_PROVIDER`, `OPENAI_BASE_URL`, `AUTOSELL_OPENAI_MODEL`, `AUTOSELL_CLAUDE_MODEL`. Panelden kaydedilen ayarlar bunların önüne geçer.
- **Site değişirse:** Ayarlar → Platformlar → Gelişmiş bölümünden ilan verme adresi, arama adresi şablonu, ilan bağlantısı kalıpları ve arama sonucu kart seçicileri kod değiştirmeden güncellenebilir.
- **Tarayıcı:** `headless` (görünmez mod), `channel: "chrome"` (bilgisayarda kurulu Chrome'u kullan), eylemler arası bekleme süreleri ve kullanıcı müdahalesi zaman aşımı ayarlanabilir.

## Telegram bildirimi

1. Telegram'da **@BotFather** ile bir bot oluştur ve verdiği anahtarı kopyala.
2. Botuna bir mesaj gönder. Ardından `https://api.telegram.org/bot<ANAHTAR>/getUpdates` adresinden `chat.id` değerini al.
3. İkisini **Ayarlar → Bildirimler** bölümüne gir ve "Test mesajı gönder" ile dene.

## Sık sorulanlar

- **Tarayıcı açılıyor ama giriş istiyor:** Önce `autosell giris sahibinden` ya da paneldeki "Giriş yap" ile bir kez giriş yap. Oturum süresi dolarsa işlem giriş adımında seni bekler.
- **CAPTCHA / SMS doğrulaması çıktı:** Panelde uyarı görünür. Adımı tarayıcı penceresinde ya da paneldeki uzaktan kontrol ekranından tamamla; otomasyon kendiliğinden devam eder.
- **Kategori ya da bir alan yanlış seçildi:** Onaylı modda son adımda tarayıcıda düzeltip yayınlayabilirsin. Kalıcı çözüm için taslaktaki kategori yolunu ya da özellik adlarını sitedeki adlarla güncelle.
- **Arama sayfasında ilan okunamadı:** Arama bağlantısının doğru olduğundan emin ol. Site tasarımı değiştiyse kart seçicilerini güncelle; genel bağlantı tabanlı okuma çoğu durumda yine de çalışır.
- **Ücretli ilan / doping:** AutoSell hiçbir ödeme yapmaz. Kategori ücretliyse ödeme ekranında durur ve karar sana kalır.

## Geliştirme

```bash
pip install -e ".[dev]"
pytest                     # birim + API + sahte site üzerinde uçtan uca tarayıcı testleri
```

- `tests/fixtures/mock_sites/`: Sahibinden ve Letgo akışlarını taklit eden, çevrimdışı çalışan sahte siteler. Uçtan uca testler gerçek sitelere hiç bağlanmaz.

```
src/autosell/
  ai/            sağlayıcılar (Claude, OpenAI uyumlu), şemalar, Türkçe talimatlar
  listing/       ilan üretici, başlık puanlayıcı, platform kuralları
  automation/    tarayıcı iş parçacıkları, sayfa anlık görüntüsü, form doldurucu,
                 yapay zekâ adım ajanı, güvenlik korumaları, platform adaptörleri
  market/        arama sonucu okuma, fiyat araştırması, fırsat puanı, yapay zekâ değerlendirmesi, Telegram
  web/           FastAPI API + tek sayfalık arayüz (derleme gerektirmez)
  service.py     panel ve komut satırının kullandığı işlemler
  cli.py         komut satırı
```

