"""Yapılandırılmış çıktı (JSON Schema) tanımları.

Hem Claude structured outputs hem de OpenAI strict json_schema ile uyumlu olacak
şekilde: tüm nesnelerde additionalProperties=false, tüm alanlar zorunlu,
minLength/maximum gibi kısıtlar yok.
"""

from __future__ import annotations

from typing import Any

STR: dict[str, Any] = {"type": "string"}
STR_LIST: dict[str, Any] = {"type": "array", "items": {"type": "string"}}
NUM: dict[str, Any] = {"type": "number"}
INT: dict[str, Any] = {"type": "integer"}
BOOL: dict[str, Any] = {"type": "boolean"}

CONDITIONS = [
    "Sıfır",
    "Sıfır Ayarında",
    "Çok İyi",
    "İyi",
    "Orta",
    "Kusurlu",
    "Arızalı / Parça",
    "Bilinmiyor",
]


def obj(properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


def enum(values: list[str]) -> dict[str, Any]:
    return {"type": "string", "enum": values}


def listing_schema(platforms: list[str]) -> dict[str, Any]:
    product = obj(
        {
            "ad": STR,
            "marka": STR,
            "model": STR,
            "durum": enum(CONDITIONS),
            "one_cikanlar": STR_LIST,
            "kusurlar": STR_LIST,
            "kutu_icerigi": STR_LIST,
            "anahtar_kelimeler": STR_LIST,
            "eksik_bilgiler": STR_LIST,
            "uyarilar": STR_LIST,
            "kapak_fotografi": INT,
        }
    )
    platform_listing = obj(
        {
            "kategori_yolu": STR_LIST,
            "baslik_adaylari": STR_LIST,
            "aciklama": STR,
            "ozellikler": {"type": "array", "items": obj({"ad": STR, "deger": STR})},
        }
    )
    props: dict[str, Any] = {"urun": product}
    for platform in platforms:
        props[platform] = platform_listing
    return obj(props)


def field_choice_schema(fields: list[tuple[str, list[str]]]) -> dict[str, Any]:
    """Form alanları için değer seçimi. fields: [(anahtar, seçenekler)] — seçenek yoksa serbest metin."""
    props: dict[str, Any] = {}
    for key, options in fields:
        props[key] = enum(list(dict.fromkeys([*options, ""]))) if options else STR
    return obj(props)


def option_pick_schema(options: list[str]) -> dict[str, Any]:
    return obj({"secim": enum(list(dict.fromkeys([*options, "YOK"]))), "gerekce": STR})


AGENT_ACTIONS = ["tikla", "yaz", "sec", "isaretle", "bekle", "tamam", "kullanici"]


def agent_action_schema() -> dict[str, Any]:
    return obj({"eylem": enum(AGENT_ACTIONS), "oge": STR, "deger": STR, "aciklama": STR})


def deal_eval_schema() -> dict[str, Any]:
    return obj(
        {
            "ayni_urun_emsal_orani": NUM,
            "duzeltilmis_piyasa_degeri": NUM,
            "hizli_satis_fiyati": NUM,
            "tahmini_net_kar": NUM,
            "risk_seviyesi": enum(["dusuk", "orta", "yuksek"]),
            "riskler": STR_LIST,
            "firsat_mi": BOOL,
            "pazarlik_teklifi": NUM,
            "yorum": STR,
            "kaynaklar": STR_LIST,
        }
    )


def listing_card_schema() -> dict[str, Any]:
    """Sayfa metninden ilan kartı çıkarımı (seçiciler tutmadığında yedek)."""
    item = obj({"baslik": STR, "fiyat": STR, "konum": STR, "tarih": STR, "baglanti": STR})
    return obj({"ilanlar": {"type": "array", "items": item}})
