"""Türkçe metin yardımcıları: harf dönüşümü, normalleştirme, benzerlik, fiyat
ayrıştırma ve ilan metni temizleme."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable, Sequence

# ----------------------------------------------------------------- harf/biçim

_TR_UPPER = str.maketrans({"i": "İ", "ı": "I"})
_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})
_FOLD = str.maketrans(
    {
        "ç": "c", "Ç": "c", "ğ": "g", "Ğ": "g", "ı": "i", "İ": "i", "ö": "o", "Ö": "o",
        "ş": "s", "Ş": "s", "ü": "u", "Ü": "u", "â": "a", "Â": "a", "î": "i", "Î": "i",
        "û": "u", "Û": "u", "²": "2", "³": "3",
    }
)


def tr_upper(text: str) -> str:
    return text.translate(_TR_UPPER).upper()


def tr_lower(text: str) -> str:
    return text.translate(_TR_LOWER).lower()


def tr_capitalize(word: str) -> str:
    if not word:
        return word
    return tr_upper(word[0]) + tr_lower(word[1:])


def ascii_fold(text: str) -> str:
    text = text.translate(_FOLD)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


_UNIT_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(gb|tb|mb|mp|hz|ghz|mhz|mah|w|kw|km|cc|kg|lt|ml|cm|mm|inc|inch|m2|mt)\b"
)
_SECOND_HAND_RE = re.compile(r"\b(?:2\s*\.?\s*el|ikinci\s+el)\b")


def normalize(text: str) -> str:
    """Karşılaştırma için: küçük harf, aksansız, birimler bitişik, noktalama yok."""
    if not text:
        return ""
    s = ascii_fold(tr_lower(text))
    s = re.sub(r"(?<=\d)[.](?=\d{3}\b)", "", s)  # 32.500 -> 32500
    s = _UNIT_RE.sub(lambda m: m.group(1).replace(",", ".") + m.group(2), s)
    s = re.sub(r"[^a-z0-9.]+", " ", s)
    s = re.sub(r"(?<!\d)\.|\.(?!\d)", " ", s)
    return re.sub(r"\s+", " ", s).strip()


# Ürün kimliğine katkısı olmayan (durum/pazarlama) kelimeler
STOPWORDS = frozenset(
    """
    satilik satlik sahibinden sahibi acil acill uygun uygundur fiyat fiyata fiyatli ve ile icin cok super
    firsat firsati kacmaz kacirmayin orijinal orjinal sifir ayarinda garantili garanti faturali fatura
    kutulu kutu kutusu az kullanilmis kullanildi hatasiz sorunsuz tertemiz temiz bakimli full takasli
    takas yok var degisensiz boyasiz gibi yeni el sadece tek model modeli satiyorum satilir durumda
    mukemmel harika iyi guzel kondisyon kondisyonda ayar ayarinda veya olan en bu da de ki mi pazarlik
    payi indirimli indirim kargo bedava ucretsiz hediye hediyeli ozel
    """.split()
)


def tokens(text: str, drop_stopwords: bool = True) -> list[str]:
    s = normalize(text)
    s = _SECOND_HAND_RE.sub(" ", s)
    out = []
    for tok in s.split():
        if drop_stopwords and tok in STOPWORDS:
            continue
        if len(tok) == 1 and not tok.isdigit():
            continue
        out.append(tok)
    return out


# ----------------------------------------------------------------- benzerlik


def _numbers(norm: str) -> set[str]:
    return set(re.findall(r"\d+(?:\.\d+)?", norm))


def similarity(a: str, b: str) -> float:
    """Kısa etiket/seçenek metinleri için 0..1 benzerlik."""
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    if na.replace(" ", "") == nb.replace(" ", ""):
        return 0.97
    num_a, num_b = _numbers(na), _numbers(nb)
    ta, tb = set(na.split()), set(nb.split())
    inter = ta & tb
    shorter, longer = (na, nb) if len(na) <= len(nb) else (nb, na)
    if re.search(r"(?:^| )" + re.escape(shorter) + r"(?: |$)", longer):
        score = 0.82 + 0.13 * (len(shorter) / len(longer))
    else:
        jacc = len(inter) / len(ta | tb)
        contain = len(inter) / min(len(ta), len(tb))
        seq = SequenceMatcher(None, na, nb).ratio()
        score = max(seq * 0.95, 0.55 * contain + 0.45 * jacc)
    if num_a and num_b and num_a != num_b:
        score = min(score, 0.45)
    elif bool(num_a) != bool(num_b) and score < 0.9:
        score *= 0.9
    return round(min(score, 1.0), 4)


def best_match(query: str, options: Sequence[str], threshold: float = 0.0) -> tuple[int, float]:
    """En iyi seçeneğin indeksini ve skorunu döner; bulunamazsa (-1, 0)."""
    best_i, best_s = -1, 0.0
    for i, opt in enumerate(options):
        s = similarity(query, opt)
        if s > best_s:
            best_i, best_s = i, s
    if best_s < threshold:
        return -1, best_s
    return best_i, best_s


def contains_phrase(haystack: str, needle: str) -> bool:
    nh, nn = normalize(haystack), normalize(needle)
    if not nn:
        return False
    return re.search(r"(?:^| )" + re.escape(nn) + r"(?: |$)", nh) is not None


# ------------------------------------------------------------------- fiyatlar

_NUM = r"(\d{1,3}(?:[.\s  ]\d{3})+|\d+)(?:,(\d{1,2}))?"
_PRICE_AFTER = re.compile(_NUM + r"\s*(TL|₺|TRY|USD|\$|EUR|€|GBP|£)", re.IGNORECASE)
_PRICE_BEFORE = re.compile(r"(TL|₺|TRY|USD|\$|EUR|€|GBP|£)\s*" + _NUM, re.IGNORECASE)
_CURRENCY = {"tl": "TL", "₺": "TL", "try": "TL", "usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR",
             "gbp": "GBP", "£": "GBP"}


def _to_float(whole: str, dec: str | None) -> float:
    whole = re.sub(r"[.\s  ]", "", whole)
    return float(whole + ("." + dec if dec else ""))


def parse_price(text: str | None) -> tuple[float | None, str]:
    """'32.500 TL', '₺31.000', '1.250,50 TL' gibi metinlerden (tutar, para birimi) çıkarır."""
    if not text:
        return None, "TL"
    t = text.replace("\n", " ")
    m = _PRICE_AFTER.search(t)
    if m:
        return _to_float(m.group(1), m.group(2)), _CURRENCY[m.group(3).lower()]
    m = _PRICE_BEFORE.search(t)
    if m:
        return _to_float(m.group(2), m.group(3)), _CURRENCY[m.group(1).lower()]
    m = re.search(_NUM, t)
    if m:
        try:
            return _to_float(m.group(1), m.group(2)), "TL"
        except ValueError:
            return None, "TL"
    return None, "TL"


def format_price(value: float | None, currency: str = "TL") -> str:
    if value is None:
        return "-"
    txt = f"{value:,.0f}".replace(",", ".")
    return f"{txt} {currency}"


# ---------------------------------------------------------- ilan metni temizliği

_URL_RE = re.compile(
    r"(?:https?://|www\.)\S+|\b[\w-]+\.(?:com|net|org|info|biz|io|me|co|com\.tr|net\.tr|org\.tr)\b(?:/\S*)?",
    re.IGNORECASE,
)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b")
_PHONE_RE = re.compile(
    r"(?<!\d)(?:\+?90[\s.-]*)?\(?0?\s*[2-5]\d{2}\)?[\s.-]*\d{3}[\s.-]*\d{2}[\s.-]*\d{2}(?!\d)"
)
_HANDLE_RE = re.compile(r"(?<![\w@])@[A-Za-z0-9_.]{3,}")
_EMOJI_RE = re.compile(
    "["
    "\U0001F000-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U00002B00-\U00002BFF"
    "\U0000FE0F\U0000200D\U000020E3"
    "]+"
)


def strip_emoji(text: str) -> str:
    return _EMOJI_RE.sub("", text)


def remove_contact_info(text: str) -> str:
    text = _URL_RE.sub("", text)
    text = _EMAIL_RE.sub("", text)
    text = _PHONE_RE.sub("", text)
    text = _HANDLE_RE.sub("", text)
    return text


def has_contact_info(text: str) -> bool:
    return bool(_URL_RE.search(text) or _EMAIL_RE.search(text) or _PHONE_RE.search(text))


def clean_whitespace(text: str) -> str:
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.replace("\r\n", "\n").split("\n")]
    out = "\n".join(lines)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def sanitize_listing_text(text: str, allow_emoji: bool) -> str:
    text = remove_contact_info(text or "")
    if not allow_emoji:
        text = strip_emoji(text)
    return clean_whitespace(text)


# ------------------------------------------------------------- başlık biçimi

KNOWN_CASING = {
    w.lower(): w
    for w in """iPhone iPad iMac MacBook AirPods AirTag iOS PlayStation PS5 PS4 PS3 Xbox GB TB MB RAM SSD HDD
    NVMe USB USB-C HDMI 4K 8K 5G 4G LTE TL LED OLED QLED TV CPU GPU RTX GTX AMD RX BMW VW HP LG JBL MSI DJI
    ASUS TCL AEG IKEA dCi TDI TSI TCe CDI HDi VTEC GTI AMG SUV LPG CNG ABS ESP ANC NFC GPS SIM eSIM DSLR
    Wi-Fi Bluetooth XL XXL XS 2XL 3XL ROG UHD FHD HD PC i3 i5 i7 i9 m² km cc""".split()
}
KNOWN_CASING["m2"] = "m²"
_UNIT_CASING = {"gb": "GB", "tb": "TB", "mb": "MB", "mp": "MP", "hz": "Hz", "ghz": "GHz", "mhz": "MHz",
                "mah": "mAh", "w": "W", "cc": "cc", "km": "km", "inç": "inç"}
SMALL_WORDS = frozenset({"ve", "ile", "veya", "için", "de", "da", "ya", "mi", "mı"})


def _style_word(word: str, first: bool) -> str:
    core = word.strip("()[]{}\"'.,;:!?")
    if not core:
        return word
    lower = tr_lower(core)
    key = ascii_fold(lower)  # "IPHONE" -> "ıphone" -> "iphone"
    unit = re.fullmatch(r"(\d+(?:[.,]\d+)?)(gb|tb|mb|mp|hz|ghz|mhz|mah|w|cc|km|inç)", lower)
    if key in KNOWN_CASING:
        styled = KNOWN_CASING[key]
    elif unit:
        styled = unit.group(1) + _UNIT_CASING[unit.group(2)]
    elif re.search(r"\d", core) and re.search(r"[a-zA-Z]", core) and len(core) <= 8 and core.isascii():
        styled = core.upper()  # model kodları: s21 -> S21, a54 -> A54
    elif any(ch.isupper() for ch in core[1:]) and not core.isupper():
        styled = core  # iPhone, MacBook gibi özel yazımlar
    elif lower in SMALL_WORDS and not first:
        styled = lower
    else:
        styled = tr_capitalize(core)
    return word.replace(core, styled, 1)


def apply_title_style(title: str, style: str) -> str:
    title = re.sub(r"\s+", " ", title).strip()
    if style == "upper":
        return tr_upper(title)
    words = title.split(" ")
    if style == "sentence":
        if not words:
            return title
        out = []
        for i, w in enumerate(words):
            low = tr_lower(w)
            out.append(KNOWN_CASING.get(low.strip(".,"), w if i else tr_upper(w[:1]) + w[1:]))
        return " ".join(out)
    return " ".join(_style_word(w, i == 0) for i, w in enumerate(words))


_TITLE_SEPARATORS = (" | ", " - ", " – ", " — ", " / ", ", ", "; ")


def smart_truncate(text: str, max_len: int) -> str:
    """Kelime bölmeden kısaltır; "Pil %89" gibi etiket-değer çiftinin yalnız etiketini bırakmaz."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    words = text.split(" ")
    kept: list[str] = []
    for word in words:
        if len(" ".join([*kept, word])) > max_len:
            break
        kept.append(word)
    if not kept:
        return text[:max_len].strip()
    following = words[len(kept)] if len(kept) < len(words) else ""
    if following[:1].isdigit() or following[:1] in "%(#":
        kept = kept[:-1] or kept  # değeri kesilen etiketi de at
    return " ".join(kept).rstrip(" -–—|/,;:.(").strip()


def fit_title(title: str, max_len: int) -> str:
    """Başlığı sınırı aşmayacak şekilde kısaltır: önce parantezli ekleri, sonra ayraçla
    ayrılmış son parçaları atar; olmazsa kelime sınırında keser."""
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) <= max_len:
        return title
    reduced = re.sub(r"\s*\([^)]*\)", "", title).strip()
    if len(reduced) <= max_len:
        return reduced
    by_words = smart_truncate(reduced, max_len)
    best_segment = ""
    for sep in _TITLE_SEPARATORS:
        if sep not in reduced:
            continue
        parts = reduced.split(sep)
        while len(parts) > 1 and len(sep.join(parts)) > max_len:
            parts.pop()
        candidate = sep.join(parts).strip()
        if len(candidate) <= max_len and len(candidate) > len(best_segment):
            best_segment = candidate
    if best_segment and len(best_segment) >= 0.75 * len(by_words):
        return best_segment
    return by_words


def unique_preserve(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = normalize(item)
        if item and key and key not in seen:
            seen.add(key)
            out.append(item)
    return out
