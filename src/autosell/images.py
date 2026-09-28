"""Fotoğraf işlemleri: yüklenen fotoğrafları düzeltme/küçültme ve yapay zekâya
gönderilecek hale getirme. EXIF verileri (GPS konumu dahil) silinir."""

from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageOps

from .ai.base import ImageInput

try:  # iPhone HEIC fotoğrafları için isteğe bağlı destek: pip install pillow-heif
    from pillow_heif import register_heif_opener

    register_heif_opener()
except ImportError:  # pragma: no cover
    pass

ALLOWED_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp", ".gif"}


def _open(source: bytes | Path) -> Image.Image:
    img = Image.open(io.BytesIO(source) if isinstance(source, bytes) else source)
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            background.paste(img, mask=img.split()[-1])
            img = background
        else:
            img = img.convert("RGB")
    elif img.mode == "L":
        img = img.convert("RGB")
    return img


def save_upload(source: bytes | Path, dest: Path, max_side: int = 2048, quality: int = 90) -> Path:
    """Fotoğrafı döndürme düzeltmesiyle JPEG olarak kaydeder (meta veriler silinir)."""
    img = _open(source)
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    dest = dest.with_suffix(".jpg")
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, "JPEG", quality=quality, optimize=True)
    return dest


def for_ai(path: Path, max_side: int = 1280, quality: int = 85) -> ImageInput:
    img = _open(path)
    img.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=quality, optimize=True)
    return ImageInput(media_type="image/jpeg", data_b64=base64.standard_b64encode(buf.getvalue()).decode())
