"""Telegram bildirimleri."""

from __future__ import annotations

import html
import json
import logging
import urllib.error
import urllib.request

from ..models import Deal, MarketListing
from ..textutil import format_price

log = logging.getLogger(__name__)


def send_telegram(token: str, chat_id: str, text: str, timeout: float = 15) -> tuple[bool, str]:
    if not token or not chat_id:
        return False, "Telegram bot anahtarı ya da sohbet kimliği (chat id) tanımlı değil."
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": False}
    ).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode() or "{}")
            return bool(body.get("ok")), body.get("description", "")
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("description", "")
        except Exception:  # pragma: no cover
            detail = str(exc)
        return False, f"Telegram hatası: {detail}"
    except (urllib.error.URLError, TimeoutError) as exc:
        return False, f"Telegram'a ulaşılamadı: {exc}"


def deal_message(deal: Deal, listing: MarketListing) -> str:
    e = html.escape
    risks = "".join(f"\n⚠️ {e(f.text)}" for f in deal.risk_flags[:3])
    ai = ""
    if deal.ai and deal.ai.get("yorum"):
        ai = f"\n🤖 {e(str(deal.ai['yorum'])[:300])}"
    return (
        f"🔥 <b>Fırsat ({deal.score:.0f}/100)</b> — {e(listing.platform)}\n"
        f"<b>{e(listing.title)}</b>\n"
        f"💰 Fiyat: {format_price(listing.price)} | Piyasa: {format_price(deal.est_value)}\n"
        f"📈 Tahmini kâr: {format_price(deal.est_profit)} (%{(deal.margin_pct or 0):.0f})\n"
        f"📍 {e(listing.location or '-')}"
        f"{risks}{ai}\n{e(listing.url)}"
    )
