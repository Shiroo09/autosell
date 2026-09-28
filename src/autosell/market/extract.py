"""Arama sonuç sayfalarından ilan kartlarını ve detay sayfasından açıklama/özellikleri
çıkarır.

Önce platformun CSS seçicileri denenir (ayarlardan değiştirilebilir). Site
tasarımı değişse bile çalışsın diye ayrıca genel yöntem uygulanır: ilan detay
bağlantısı kalıbına uyan her bağlantıdan yukarı çıkılarak içinde fiyat geçen en
küçük kapsayıcı "kart" kabul edilir.
"""

from __future__ import annotations

import re
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import Page

from ..config import PlatformSettings
from ..models import ScrapedListing
from ..textutil import normalize, parse_price

CARDS_JS = r"""
(args) => {
  const regs = (args.patterns || []).map(p => new RegExp(p));
  const sel = args.selectors || {};
  const clean = s => (s || '').replace(/[\s ]+/g, ' ').trim();
  // Metin parçaları: CSS düzeninden bağımsız olarak her metin düğümü ayrı parça
  const lines = (root) => {
    const out = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null);
    let node, last = null, buf = '';
    while ((node = walker.nextNode())) {
      const parent = node.parentElement;
      if (!parent || ['SCRIPT', 'STYLE', 'NOSCRIPT'].includes(parent.tagName)) continue;
      const t = clean(node.nodeValue);
      if (!t) continue;
      if (parent === last) { buf += ' ' + t; } else { if (buf) out.push(buf); buf = t; last = parent; }
    }
    if (buf) out.push(buf);
    return out;
  };
  const PRICE =/(\d{1,3}(?:[.\s ]\d{3})+|\d+)(?:,\d{1,2})?\s*(TL|₺|USD|EUR|\$|€)|(₺|TL)\s*\d/i;
  const idFromHref = (href) => { for (const r of regs) { const m = (href || '').match(r); if (m) return m[1]; } return null; };
  const imgOf = (card) => {
    const img = card.querySelector('img');
    if (!img) return '';
    return img.currentSrc || img.getAttribute('data-src') || img.src || (img.getAttribute('srcset') || '').split(' ')[0] || '';
  };
  const out = [];
  const seen = new Set();
  const q = (card, s) => { if (!s) return null; try { return card.querySelector(s); } catch (e) { return null; } };
  const txt = (el) => el ? (el.innerText || el.textContent || '') : '';
  if (sel.card) {
    let cards = [];
    try { cards = Array.from(document.querySelectorAll(sel.card)); } catch (e) { cards = []; }
    for (const card of cards) {
      const titleEl = q(card, sel.title);
      let link = titleEl ? (titleEl.closest('a[href]') || titleEl.querySelector('a[href]')) : null;
      if (!link) link = card.querySelector('a[href]') || card.closest('a[href]');
      const href = link ? link.href : '';
      const id = (sel.id_attr && card.getAttribute(sel.id_attr)) || idFromHref(href);
      if (!id || seen.has(id)) continue;
      seen.add(id);
      out.push({
        id, url: href,
        title: clean(txt(titleEl) || (link && (link.getAttribute('title') || link.innerText))),
        price: clean(txt(q(card, sel.price))),
        location: clean(txt(q(card, sel.location)).replace(/\n+/g, ' / ')),
        date: clean(txt(q(card, sel.date)).replace(/\n+/g, ' ')),
        image: imgOf(card), lines: lines(card).slice(0, 14), source: 'selector',
      });
    }
  }
  for (const a of document.querySelectorAll('a[href]')) {
    const id = idFromHref(a.href);
    if (!id || seen.has(id)) continue;
    let node = a, card = null;
    for (let i = 0; i < 9 && node && node !== document.body; i++) {
      const ids = new Set(Array.from(node.querySelectorAll('a[href]')).map(x => idFromHref(x.href)).filter(Boolean));
      if (ids.size > 1) break;
      if (PRICE.test(node.innerText || '')) { card = node; break; }
      node = node.parentElement;
    }
    if (!card) continue;
    seen.add(id);
    // Başlık: bağlantının title özniteliği ya da kart içindeki başlık öğesi; yoksa Python tarafı seçer
    const sameLinks = [card, ...card.querySelectorAll('a[href]')].filter(x => x.matches && x.matches('a[href]') && idFromHref(x.href) === id);
    let title = sameLinks.map(x => clean(x.getAttribute('title') || '')).find(Boolean) || '';
    if (!title) {
      const heading = card.querySelector('h1, h2, h3, h4, [class*="title" i], [class*="baslik" i]');
      if (heading) title = clean(heading.innerText || heading.textContent);
    }
    out.push({ id, url: a.href, title, price: '', location: '', date: '', image: imgOf(card), lines: lines(card).slice(0, 14), source: 'generic' });
  }
  return out;
}
"""

DETAIL_JS = r"""
() => {
  const clean = s => (s || '').replace(/[\s ]+/g, ' ').trim();
  const pick = (sels) => { for (const s of sels) { const el = document.querySelector(s); if (el && clean(el.innerText)) return el; } return null; };
  const descEl = pick(['#classifiedDescription', '[data-aut-id="itemDescriptionContent"]', '[itemprop="description"]',
                       '[class*="description" i]', '[class*="aciklama" i]', '[data-testid*="description" i]']);
  let description = descEl ? descEl.innerText.trim() : '';
  if (!description) {
    const blocks = Array.from(document.querySelectorAll('main p, main div, article p, article div, p'))
      .map(e => (e.innerText || '').trim()).filter(t => t.length > 80 && t.length < 6000);
    blocks.sort((a, b) => b.length - a.length);
    description = blocks[0] || '';
  }
  const attrs = {};
  const add = (k, v) => { k = clean(k).replace(/[:：]$/, ''); v = clean(v); if (k && v && k.length < 50 && v.length < 120 && !(k in attrs)) attrs[k] = v; };
  document.querySelectorAll('ul.classifiedInfoList li, [class*="info" i] li, [class*="detail" i] li, [class*="attribute" i] li, [class*="param" i] li').forEach(li => {
    const kids = Array.from(li.children).filter(c => clean(c.innerText));
    if (kids.length >= 2) add(kids[0].innerText, kids[kids.length - 1].innerText);
  });
  document.querySelectorAll('dl').forEach(dl => {
    const dts = dl.querySelectorAll('dt');
    dts.forEach(dt => { const dd = dt.nextElementSibling; if (dd && dd.tagName === 'DD') add(dt.innerText, dd.innerText); });
  });
  document.querySelectorAll('table tr').forEach(tr => {
    const cells = tr.querySelectorAll('th, td');
    if (cells.length === 2) add(cells[0].innerText, cells[1].innerText);
  });
  const h1 = document.querySelector('h1');
  const priceEl = pick(['.classifiedInfo h3', '[data-aut-id="itemPrice"]', '[class*="price" i]', '[class*="fiyat" i]']);
  return { title: h1 ? clean(h1.innerText) : document.title, price: priceEl ? clean(priceEl.innerText) : '',
           description: description.slice(0, 6000), attributes: attrs, url: location.href };
}
"""

_MONTHS = ("ocak", "subat", "mart", "nisan", "mayis", "haziran", "temmuz", "agustos", "eylul", "ekim", "kasim", "aralik")
_RELATIVE = ("bugun", "dun", "saat once", "dakika once", "gun once", "hafta once", "ay once", "az once", "yeni")
PROVINCES = frozenset(
    normalize(p)
    for p in """Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin Aydın Balıkesir Bartın
    Batman Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale Çankırı Çorum Denizli Diyarbakır Düzce Edirne
    Elazığ Erzincan Erzurum Eskişehir Gaziantep Giresun Gümüşhane Hakkari Hatay Iğdır Isparta İstanbul İzmir
    Kahramanmaraş Karabük Karaman Kars Kastamonu Kayseri Kilis Kırıkkale Kırklareli Kırşehir Kocaeli Konya Kütahya
    Malatya Manisa Mardin Mersin Muğla Muş Nevşehir Niğde Ordu Osmaniye Rize Sakarya Samsun Şanlıurfa Siirt Sinop
    Sivas Şırnak Tekirdağ Tokat Trabzon Tunceli Uşak Van Yalova Yozgat Zonguldak""".split()
)


def _is_date_line(line: str) -> bool:
    n = normalize(line)
    return any(n.startswith(r) or f" {r}" in f" {n}" for r in _RELATIVE) or any(m in n.split() for m in _MONTHS)


def _is_location_line(line: str) -> bool:
    parts = [normalize(p) for p in re.split(r"[,/]| - ", line) if p.strip()]
    return any(p in PROVINCES for p in parts) and len(line) <= 60


def parse_card(raw: dict[str, Any], platform: str) -> ScrapedListing | None:
    lines: list[str] = raw.get("lines") or []
    price_text = raw.get("price") or next((ln for ln in lines if parse_price(ln)[0] and re.search(r"TL|₺|\$|€|USD|EUR", ln)), "")
    price, currency = parse_price(price_text)
    title = (raw.get("title") or "").strip()
    location = (raw.get("location") or "").strip()
    date_text = (raw.get("date") or "").strip()
    if not location:
        location = next((ln for ln in lines if _is_location_line(ln)), "")
    if not date_text:
        date_text = next((ln for ln in lines if _is_date_line(ln) and not re.search(r"TL|₺|\$|€", ln)), "")
    if not title or len(title) < 4:
        rest = [ln for ln in lines if ln not in (price_text, location, date_text) and not re.search(r"TL|₺", ln)]
        title = max(rest, key=len, default=title)
    if not title:
        return None
    return ScrapedListing(
        platform=platform,
        external_id=str(raw["id"]),
        url=raw.get("url", ""),
        title=title[:200],
        price=price,
        currency=currency,
        location=location[:80],
        date_text=date_text[:40],
        image_url=(raw.get("image") or "")[:500],
    )


def extract_cards(page: Page, platform: str, ps: PlatformSettings) -> list[ScrapedListing]:
    try:
        raw_items = page.evaluate(
            CARDS_JS, {"patterns": ps.listing_url_patterns, "selectors": ps.card_selectors or {}}
        )
    except PlaywrightError:
        return []
    out: list[ScrapedListing] = []
    for raw in raw_items:
        item = parse_card(raw, platform)
        if item:
            out.append(item)
    return out


def extract_details(page: Page) -> dict[str, Any]:
    try:
        data = page.evaluate(DETAIL_JS)
    except PlaywrightError:
        return {}
    price, currency = parse_price(data.get("price", ""))
    data["price_value"] = price
    data["currency"] = currency
    return data
