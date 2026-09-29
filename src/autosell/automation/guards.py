"""Güvenlik ve durum algılama: ödeme, CAPTCHA, giriş, doğrulama kodu, başarı."""

from __future__ import annotations

import re

from ..textutil import normalize
from .driver import Clickable, Snapshot

# Asla tıklanmayacak ücretli işlemler (normalize edilmiş)
PAYMENT_WORDS = (
    "odeme", " ode ", "satin al", "sepete", "kredi kart", "banka kart", "kart numarasi", "kart no", "cvv", "cvc",
    "son kullanma", "doping al", "dopingleri satin", "one cikar", "vitrine ekle", "paket al", "paketi al",
    "hemen al", "abone ol", "ucretli", "odemeyi", "tahsil",
)
_PRICE_IN_TEXT = re.compile(r"(?:₺\s*\d|\d[\d.,]*\s*(?:tl|₺)\b)", re.IGNORECASE)

CAPTCHA_FRAMES = ("recaptcha", "hcaptcha", "turnstile", "challenges.cloudflare", "arkoselabs", "funcaptcha", "geetest", "captcha")
CAPTCHA_TEXTS = (
    "robot olmadiginizi", "robot olmadigini", "guvenlik dogrulamasi", "ben robot degilim", "im not a robot",
    "verify you are human", "olagan disi erisim", "olagandisi erisim", "unusual traffic", "checking your browser",
    "insan oldugunuzu", "guvenlik kontrolu",
)
VERIFY_TEXTS = (
    "dogrulama kodu", "sms kodu", "tek kullanimlik", "onay kodu", "telefonunuza gonderilen", "telefonuna gonderilen",
    "kodu girin", "kodu giriniz", "cep telefonu dogrulama", "kimlik dogrulama",
)
SUCCESS_TEXTS = (
    "ilaniniz yayinda", "ilanin yayinda", "ilaniniz yayina alin", "ilaniniz basariyla", "ilanin basariyla",
    "ilaniniz olusturuldu", "ilaniniz onaya gonderildi", "kontrol edildikten sonra yayina", "incelendikten sonra yayina",
    "tebrikler ilaniniz", "ilaniniz alindi", "ilaniniz kaydedildi",
)


def is_payment_text(text: str) -> bool:
    n = " " + normalize(text) + " "
    if any(w in n for w in PAYMENT_WORDS):
        return True
    return bool(_PRICE_IN_TEXT.search(text or ""))


def is_payment_clickable(c: Clickable) -> bool:
    return is_payment_text(c.text) or any(w in (c.href or "").lower() for w in ("odeme", "payment", "checkout", "sepet"))


def is_payment_page(snap: Snapshot) -> bool:
    for f in snap.fields:
        blob = normalize(f"{f.label} {f.name} {f.placeholder} {f.autocomplete}")
        if f.autocomplete.startswith("cc-") or any(
            w in blob for w in ("kart numarasi", "card number", "cardnumber", "cvv", "cvc", "son kullanma", "expiry")
        ):
            return True
    return False


def is_captcha(snap: Snapshot) -> bool:
    if any(any(k in src.lower() for k in CAPTCHA_FRAMES) for src in snap.frames):
        return True
    text = snap.norm_text
    return any(k in text for k in CAPTCHA_TEXTS)


def needs_verification_code(snap: Snapshot) -> bool:
    text = snap.norm_text
    if not any(k in text for k in VERIFY_TEXTS):
        return False
    return any(f.kind in ("text", "number", "tel") and not f.in_chrome for f in snap.fields)


def has_password_field(snap: Snapshot) -> bool:
    return any(f.kind == "password" and not f.hidden for f in snap.fields)


def is_success(snap: Snapshot) -> bool:
    text = snap.norm_text
    return any(k in text for k in SUCCESS_TEXTS)


def extract_listing_no(text: str) -> str:
    m = re.search(r"[İi]lan\s*(?:No|Numaras[ıi])\s*[:#]?\s*(\d{5,})", text or "", re.IGNORECASE)
    return m.group(1) if m else ""
