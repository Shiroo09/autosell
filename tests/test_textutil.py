from autosell.textutil import (
    apply_title_style,
    best_match,
    fit_title,
    has_contact_info,
    normalize,
    parse_price,
    sanitize_listing_text,
    similarity,
    tokens,
    tr_lower,
    tr_upper,
)


def test_turkish_case():
    assert tr_upper("iphone ışık") == "İPHONE IŞIK"
    assert tr_lower("İSTANBUL IŞIK") == "istanbul ışık"


def test_normalize_units_and_thousands():
    assert normalize("iPhone 13 128 GB") == "iphone 13 128gb"
    assert normalize("32.500 TL") == "32500 tl"
    assert normalize("Dahili Hafıza") == "dahili hafiza"
    assert normalize("1.5 dCi") == "1.5 dci"


def test_tokens_drop_marketing_words():
    assert tokens("Sahibinden Temiz iPhone 13 128 GB 2. El Acil") == ["iphone", "13", "128gb"]


def test_similarity_numbers_must_match():
    assert similarity("iPhone 13", "iPhone 13") == 1.0
    assert similarity("128 GB", "128GB") >= 0.97
    assert similarity("iPhone 13", "iPhone 13 Pro") > 0.85
    assert similarity("iPhone 13", "iPhone 12") < 0.5
    assert similarity("Evet", "Hayır") < 0.5


def test_best_match_prefers_exact():
    options = ["iPhone 12", "iPhone 13 Pro", "iPhone 13", "iPhone 14"]
    idx, score = best_match("iphone 13", options)
    assert options[idx] == "iPhone 13" and score == 1.0
    assert best_match("Nokia 3310", options, threshold=0.7)[0] == -1


def test_parse_price_formats():
    assert parse_price("32.500 TL") == (32500.0, "TL")
    assert parse_price("₺31.000") == (31000.0, "TL")
    assert parse_price("1.250,50 TL") == (1250.5, "TL")
    assert parse_price("Fiyat: 950 USD") == (950.0, "USD")
    assert parse_price("") == (None, "TL")


def test_contact_info_is_removed():
    text = "Aramak için 0532 123 45 67, instagram @satici_tr veya www.ornek.com.tr\nTeşekkürler 🙂"
    assert has_contact_info(text)
    cleaned = sanitize_listing_text(text, allow_emoji=False)
    assert "0532" not in cleaned and "@satici_tr" not in cleaned and "ornek" not in cleaned
    assert "🙂" not in cleaned
    assert "Teşekkürler" in cleaned


def test_price_and_model_numbers_are_not_phone_numbers():
    assert not has_contact_info("iPhone 13 128 GB 32.500 TL 2021 model")


def test_title_style():
    assert apply_title_style("IPHONE 13 128gb mavi ve kutulu", "title") == "iPhone 13 128GB Mavi ve Kutulu"
    assert apply_title_style("samsung galaxy s21 ultra", "title") == "Samsung Galaxy S21 Ultra"
    assert apply_title_style("iphone 13 temiz", "upper") == "İPHONE 13 TEMİZ"


def test_fit_title_drops_segments_not_words():
    title = "Apple iPhone 13 128 GB Mavi - Kutulu Faturalı - Garantisi Devam Ediyor"
    fitted = fit_title(title, 50)
    assert len(fitted) <= 50
    assert fitted == "Apple iPhone 13 128 GB Mavi - Kutulu Faturalı"
