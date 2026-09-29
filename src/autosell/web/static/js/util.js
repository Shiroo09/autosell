// Saf yardımcılar: güvenli HTML şablonları, biçimlendirme, küçük araçlar.

// ------------------------------------------------------------------ güvenli HTML

class SafeHTML {
  constructor(s) {
    this.s = s;
  }
  toString() {
    return this.s;
  }
}

/** Güvenilir (bizim ürettiğimiz) HTML parçasını işaretler. */
export const raw = (s) => new SafeHTML(String(s ?? ''));
export const isSafe = (v) => v instanceof SafeHTML;

const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' };
export const esc = (v) => String(v ?? '').replace(/[&<>"'`]/g, (c) => ESC[c]);

function part(v) {
  if (v == null || v === false || v === true) return '';
  if (v instanceof SafeHTML) return v.s;
  if (Array.isArray(v)) return v.map(part).join('');
  return esc(v);
}

/** Etiketli şablon: tüm değerler kaçışlanır; html`` / raw() ile üretilenler olduğu gibi eklenir. */
export function html(strings, ...values) {
  let out = strings[0];
  for (let i = 0; i < values.length; i++) out += part(values[i]) + strings[i + 1];
  return new SafeHTML(out);
}

export function setHTML(target, tpl) {
  target.innerHTML = part(tpl);
  return target;
}

/** Şablondan tek bir öğe üretir. */
export function el(tpl) {
  const t = document.createElement('template');
  t.innerHTML = part(tpl).trim();
  return t.content.firstElementChild;
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

// ------------------------------------------------------------------ biçimlendirme

const nf0 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 0 });
const nf1 = new Intl.NumberFormat('tr-TR', { maximumFractionDigits: 1 });
const nfCache = new Map();

export const isNum = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));

export function fmtNum(v, digits = 0) {
  if (!isNum(v)) return '—';
  if (!digits) return nf0.format(Number(v));
  if (!nfCache.has(digits)) nfCache.set(digits, new Intl.NumberFormat('tr-TR', { maximumFractionDigits: digits }));
  return nfCache.get(digits).format(Number(v));
}

/** 32500 → "32.500 TL" */
export function fmtPrice(v, currency = 'TL') {
  if (!isNum(v)) return '—';
  return `${nf0.format(Math.round(Number(v)))} ${currency || 'TL'}`;
}

/** İşaretli fiyat: +7.388 TL / −1.200 TL */
export function fmtSignedPrice(v, currency = 'TL') {
  if (!isNum(v)) return '—';
  const n = Number(v);
  const sign = n > 0 ? '+' : n < 0 ? '−' : '';
  return `${sign}${nf0.format(Math.abs(Math.round(n)))} ${currency || 'TL'}`;
}

/** Türkçe yüzde: %31, −%5 */
export function fmtPct(v, digits = 0) {
  if (!isNum(v)) return '—';
  const n = Number(v);
  return `${n < 0 ? '−' : ''}%${fmtNum(Math.abs(n), digits)}`;
}

/** Grafik eksenleri için kısa fiyat: 32,5 bin / 1,2 mn */
export function fmtCompact(v) {
  if (!isNum(v)) return '—';
  const n = Number(v);
  const a = Math.abs(n);
  if (a >= 1e6) return `${nf1.format(n / 1e6)} mn`;
  if (a >= 1e4) return `${nf1.format(n / 1e3)} bin`;
  return nf0.format(n);
}

export function parseDate(iso) {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
}

const dtf = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' });
const dShort = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short' });
const dShortY = new Intl.DateTimeFormat('tr-TR', { day: 'numeric', month: 'short', year: 'numeric' });
const tShort = new Intl.DateTimeFormat('tr-TR', { hour: '2-digit', minute: '2-digit' });

export const fmtDateTime = (iso) => {
  const d = parseDate(iso);
  return d ? dtf.format(d) : '—';
};

export const fmtDay = (iso) => {
  const d = parseDate(iso);
  if (!d) return '—';
  return (d.getFullYear() === new Date().getFullYear() ? dShort : dShortY).format(d);
};

export const fmtTime = (iso) => {
  const d = parseDate(iso);
  return d ? tShort.format(d) : '';
};

/** "az önce", "3 dk önce", "2 sa önce", "dün", "4 gün önce", "12 Eyl" */
export function fmtRel(iso, now = Date.now()) {
  const d = parseDate(iso);
  if (!d) return '—';
  const diff = Math.round((now - d.getTime()) / 1000);
  const future = diff < 0;
  const s = Math.abs(diff);
  const suf = future ? 'sonra' : 'önce';
  if (s < 45) return future ? 'birazdan' : 'az önce';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} dk ${suf}`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} sa ${suf}`;
  const days = Math.round(h / 24);
  if (days === 1) return future ? 'yarın' : 'dün';
  if (days < 7) return `${days} gün ${suf}`;
  return fmtDay(iso);
}

/** Canlı güncellenen göreli zaman etiketi. */
export function timeAgo(iso, prefix = '') {
  if (!iso) return html`<span class="muted">—</span>`;
  return html`<time datetime="${iso}" title="${fmtDateTime(iso)}" data-rel="${iso}" data-prefix="${prefix}">${prefix}${fmtRel(iso)}</time>`;
}

export function refreshTimes(root = document) {
  const now = Date.now();
  for (const t of root.querySelectorAll('time[data-rel]')) {
    const txt = (t.dataset.prefix || '') + fmtRel(t.dataset.rel, now);
    if (t.textContent !== txt) t.textContent = txt;
  }
}

/** "32.500", "32500", "32.500,50", "32 500 TL" → sayı */
export function parsePrice(value) {
  let v = String(value ?? '').replace(/tl|₺|\s/gi, '').trim();
  if (!v) return null;
  if (v.includes(',') && v.includes('.')) v = v.replace(/\./g, '').replace(',', '.');
  else if (v.includes(',')) v = v.replace(',', '.');
  else if (/^\d{1,3}(\.\d{3})+$/.test(v)) v = v.replace(/\./g, '');
  const n = Number(v);
  return Number.isFinite(n) && n >= 0 ? n : NaN;
}

/** Fiyat alanı için gösterim: 32500 → "32.500" */
export const priceInputValue = (v) => (isNum(v) ? nf0.format(Math.round(Number(v))) : '');

/** Türkçe bulunma eki: Sahibinden'de, Letgo'da */
export function locative(word) {
  const w = String(word || '').toLocaleLowerCase('tr');
  let last = 'e';
  for (const ch of w) if ('aıoueiöü'.includes(ch)) last = ch;
  const back = 'aıou'.includes(last);
  const hard = 'çfhkpsşt'.includes(w.slice(-1));
  return `${word}'${hard ? 't' : 'd'}${back ? 'a' : 'e'}`;
}

// ------------------------------------------------------------------ araçlar

export function debounce(fn, ms = 300) {
  let t;
  const d = (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
  d.cancel = () => clearTimeout(t);
  return d;
}

/** Yalnızca http(s) ve site içi bağlantılara izin verir. */
export function safeUrl(u) {
  const s = String(u || '').trim();
  if (!s) return '';
  if (s.startsWith('/') && !s.startsWith('//')) return s;
  try {
    const url = new URL(s);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : '';
  } catch {
    return '';
  }
}

export function hostOf(u) {
  try {
    return new URL(u).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}

const PREFIX = 'autosell.';
export const store = {
  get(key, fallback = null) {
    try {
      const v = localStorage.getItem(PREFIX + key);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(PREFIX + key, JSON.stringify(value));
    } catch {
      /* gizli mod vb. */
    }
  },
  remove(key) {
    try {
      localStorage.removeItem(PREFIX + key);
    } catch {
      /* yok say */
    }
  },
};

export const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
export const uid = (p = 'u') => `${p}${Math.random().toString(36).slice(2, 9)}`;
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** Metin alanını içeriğine göre büyütür. */
export function autosize(ta, max = 0) {
  if (!ta) return;
  ta.style.height = 'auto';
  const h = ta.scrollHeight + 2;
  ta.style.height = `${max ? Math.min(h, max) : h}px`;
}

/** Puan tonu: great / good / ok / weak */
export function scoreTone(score, { good = 70, ok = 45 } = {}) {
  const s = Number(score) || 0;
  if (s >= good) return 'good';
  if (s >= ok) return 'ok';
  return 'weak';
}

export const PLATFORM_NAMES = { sahibinden: 'Sahibinden', letgo: 'Letgo' };
export const platformName = (p) => PLATFORM_NAMES[p] || p || '';

export const pluralize = (n, word) => `${fmtNum(n)} ${word}`;

/** Panoya kopyalar (güvenli olmayan bağlamda da çalışır). */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    /* yedek yönteme geç */
  }
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;top:-1000px;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  ta.remove();
  return ok;
}
