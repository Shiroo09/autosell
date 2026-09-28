// Arayüz bileşenleri: bildirimler, pencereler (sheet/modal), onay kutuları, meşgul düğmeler.
import { html, esc, el, $, $$, isSafe, uid, fmtPrice, safeUrl, platformName } from './util.js';
import { icon } from './icons.js';

// ------------------------------------------------------------------ bildirimler (toast)

const TOAST_ICONS = { success: 'checkCircle', error: 'xCircle', warning: 'alert', info: 'info' };

function toastRoot() {
  let root = document.getElementById('toasts');
  if (!root) {
    root = document.createElement('div');
    root.id = 'toasts';
    root.className = 'toasts';
    root.setAttribute('role', 'status');
    root.setAttribute('aria-live', 'polite');
    document.body.appendChild(root);
  }
  return root;
}

/**
 * @param {string} message
 * @param {{type?: 'success'|'error'|'warning'|'info', title?: string, action?: {label: string, href?: string, onClick?: Function}, timeout?: number}} opts
 */
export function toast(message, opts = {}) {
  const { type = 'info', title = '', action = null } = opts;
  const timeout = opts.timeout ?? (type === 'error' ? 8000 : 4500);
  const root = toastRoot();
  while (root.children.length >= 4) root.firstElementChild.remove();
  const node = el(html`
    <div class="toast toast-${type}" role="${type === 'error' ? 'alert' : 'status'}">
      <span class="toast-icon">${icon(TOAST_ICONS[type] || 'info', { size: 20 })}</span>
      <div class="toast-body">
        ${title ? html`<strong class="toast-title">${title}</strong>` : ''}
        <div class="toast-msg">${message}</div>
      </div>
      ${action ? (action.href
        ? html`<a class="toast-action" href="${safeUrl(action.href) || '#'}">${action.label}</a>`
        : html`<button type="button" class="toast-action">${action.label}</button>`) : ''}
      <button type="button" class="toast-close" aria-label="Kapat">${icon('x', { size: 16 })}</button>
    </div>`);
  let timer = null;
  const close = () => {
    clearTimeout(timer);
    node.classList.add('is-leaving');
    setTimeout(() => node.remove(), 180);
  };
  const arm = () => {
    clearTimeout(timer);
    if (timeout > 0) timer = setTimeout(close, timeout);
  };
  node.querySelector('.toast-close').addEventListener('click', close);
  const act = node.querySelector('.toast-action');
  if (act) {
    act.addEventListener('click', () => {
      if (action.onClick) action.onClick();
      close();
    });
  }
  node.addEventListener('pointerenter', () => clearTimeout(timer));
  node.addEventListener('pointerleave', arm);
  root.appendChild(node);
  arm();
  return { close };
}
toast.success = (m, o) => toast(m, { ...o, type: 'success' });
toast.error = (m, o) => toast(m, { ...o, type: 'error' });
toast.warning = (m, o) => toast(m, { ...o, type: 'warning' });
toast.info = (m, o) => toast(m, { ...o, type: 'info' });

/** Hata nesnesini kullanıcıya gösterir (AbortError sessizce yutulur). */
export function showError(err, fallback = 'Bir hata oluştu.') {
  if (!err || err.name === 'AbortError') return;
  if (err.status === 401) return; // giriş ekranı zaten açılıyor
  toast.error(err.message || fallback);
}

// ------------------------------------------------------------------ pencere (sheet / modal)

const stack = [];
const FOCUSABLE = 'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function lockScroll(on) {
  document.documentElement.classList.toggle('scroll-locked', on);
}

/**
 * Mobilde alttan açılan, masaüstünde ortada duran pencere.
 * @returns {{root: HTMLElement, panel: HTMLElement, body: HTMLElement, foot: HTMLElement|null, close: Function, closed: Promise<any>}}
 */
export function openSheet(opts = {}) {
  const { title = '', subtitle = '', body = '', footer = null, size = '', dismissible = true, className = '', onClose, icon: ic = '' } = opts;
  const id = uid('dlg');
  const prevFocus = document.activeElement;
  const overlay = el(html`
    <div class="overlay ${className}" data-overlay>
      <div class="sheet ${size ? `sheet-${size}` : ''}" role="dialog" aria-modal="true" aria-labelledby="${id}-t" tabindex="-1">
        <div class="sheet-handle" aria-hidden="true"></div>
        ${title ? html`
          <header class="sheet-head">
            ${ic ? html`<span class="sheet-icon">${icon(ic, { size: 20 })}</span>` : ''}
            <div class="sheet-titles">
              <h2 class="sheet-title" id="${id}-t">${title}</h2>
              ${subtitle ? html`<p class="sheet-sub">${subtitle}</p>` : ''}
            </div>
            ${dismissible ? html`<button type="button" class="btn btn-ghost btn-icon sheet-x" data-close aria-label="Kapat">${icon('x')}</button>` : ''}
          </header>` : ''}
        <div class="sheet-body"></div>
        ${footer ? html`<footer class="sheet-foot"></footer>` : ''}
      </div>
    </div>`);
  const panel = $('.sheet', overlay);
  const bodyEl = $('.sheet-body', overlay);
  const footEl = $('.sheet-foot', overlay);
  const put = (target, content) => {
    if (!target || content == null) return;
    if (content instanceof Node) target.appendChild(content);
    else if (isSafe(content)) target.innerHTML = content.s;
    else target.textContent = String(content);
  };
  put(bodyEl, body);
  put(footEl, footer);

  let resolveClosed;
  const closed = new Promise((r) => (resolveClosed = r));
  let isClosed = false;
  const close = (result) => {
    if (isClosed) return;
    isClosed = true;
    overlay.classList.add('is-leaving');
    const i = stack.indexOf(api);
    if (i >= 0) stack.splice(i, 1);
    document.removeEventListener('keydown', onKey, true);
    setTimeout(() => {
      overlay.remove();
      if (!stack.length) lockScroll(false);
    }, 180);
    if (prevFocus && prevFocus.isConnected && typeof prevFocus.focus === 'function') prevFocus.focus({ preventScroll: true });
    if (onClose) onClose(result);
    resolveClosed(result);
  };
  const onKey = (e) => {
    if (stack[stack.length - 1] !== api) return;
    if (e.key === 'Escape' && dismissible) {
      e.preventDefault();
      close(null);
    } else if (e.key === 'Tab') {
      const items = $$(FOCUSABLE, panel).filter((n) => n.offsetParent !== null || n === document.activeElement);
      if (!items.length) {
        e.preventDefault();
        panel.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === panel)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    }
  };
  overlay.addEventListener('mousedown', (e) => {
    if (e.target === overlay && dismissible) overlay.dataset.downOutside = '1';
  });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay && dismissible && overlay.dataset.downOutside === '1') close(null);
    delete overlay.dataset.downOutside;
    if (e.target.closest('[data-close]')) close(null);
  });
  document.addEventListener('keydown', onKey, true);
  const api = { root: overlay, panel, body: bodyEl, foot: footEl, close, closed };
  stack.push(api);
  lockScroll(true);
  document.body.appendChild(overlay);
  requestAnimationFrame(() => {
    // Dokunmatik cihazlarda klavyeyi kendiliğinden açmamak için metin alanlarına odaklanılmaz.
    const auto = $('[autofocus]', panel);
    const typing = auto && auto.matches('input:not([type="checkbox"]):not([type="radio"]), textarea');
    if (auto && !(typing && matchMedia('(pointer: coarse)').matches)) auto.focus({ preventScroll: true });
    else panel.focus({ preventScroll: true });
  });
  return api;
}

export const topSheet = () => stack[stack.length - 1] || null;

/**
 * Onay kutusu.
 * @returns {Promise<boolean>}
 */
export function confirmDialog({ title = 'Emin misiniz?', message = '', confirmText = 'Tamam', cancelText = 'Vazgeç', danger = false, icon: ic } = {}) {
  const sheet = openSheet({
    title,
    icon: ic || (danger ? 'alert' : 'info'),
    size: 'sm',
    className: danger ? 'is-danger' : '',
    body: isSafe(message) ? message : html`<p class="dialog-msg">${message}</p>`,
    footer: html`
      <button type="button" class="btn" data-close>${cancelText}</button>
      <button type="button" class="btn ${danger ? 'btn-danger-solid' : 'btn-primary'}" data-ok autofocus>${confirmText}</button>`,
  });
  sheet.foot.querySelector('[data-ok]').addEventListener('click', () => sheet.close(true));
  return sheet.closed.then((v) => v === true);
}

/**
 * Çok seçenekli soru. choices: [{value, label, kind: 'primary'|'danger'|''}]
 * @returns {Promise<string|null>}
 */
export function choiceDialog({ title, message = '', choices = [], icon: ic = 'info' }) {
  const sheet = openSheet({
    title,
    icon: ic,
    size: 'sm',
    body: isSafe(message) ? message : html`<p class="dialog-msg">${message}</p>`,
    footer: html`${choices.map((c) => html`<button type="button" class="btn ${c.kind === 'primary' ? 'btn-primary' : c.kind === 'danger' ? 'btn-danger' : ''}" data-choice="${c.value}">${c.label}</button>`)}`,
  });
  sheet.foot.addEventListener('click', (e) => {
    const b = e.target.closest('[data-choice]');
    if (b) sheet.close(b.dataset.choice);
  });
  return sheet.closed;
}

// ------------------------------------------------------------------ meşgul düğmeler

export function setBusy(btn, on, label) {
  if (!btn) return;
  if (on) {
    if (btn.dataset.busy === '1') return;
    btn.dataset.busy = '1';
    btn.dataset.origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.setAttribute('aria-busy', 'true');
    const text = label ?? btn.textContent.trim();
    btn.innerHTML = `<span class="spinner" aria-hidden="true"></span><span>${esc(text)}</span>`;
  } else {
    if (btn.dataset.busy !== '1') return;
    btn.innerHTML = btn.dataset.origHtml || btn.innerHTML;
    delete btn.dataset.busy;
    delete btn.dataset.origHtml;
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
  }
}

export async function withBusy(btn, label, fn) {
  setBusy(btn, true, label);
  try {
    return await fn();
  } finally {
    if (btn && btn.isConnected) setBusy(btn, false);
  }
}

// ------------------------------------------------------------------ ortak parçalar

export function spinner(size = 16) {
  return html`<span class="spinner" style="width:${size}px;height:${size}px" aria-hidden="true"></span>`;
}

export function emptyState({ icon: ic = 'box', title, text = '', action = null }) {
  return html`
    <div class="empty">
      <div class="empty-art" aria-hidden="true">${icon(ic, { size: 30 })}</div>
      <h3 class="empty-title">${title}</h3>
      ${text ? html`<p class="empty-text">${text}</p>` : ''}
      ${action || ''}
    </div>`;
}

export function callout({ tone = 'info', title = '', text = '', action = null, icon: ic }) {
  const icons = { info: 'info', warning: 'alert', danger: 'alert', success: 'checkCircle', accent: 'sparkles' };
  return html`
    <div class="callout callout-${tone}" role="${tone === 'danger' ? 'alert' : 'note'}">
      <span class="callout-icon">${icon(ic || icons[tone] || 'info', { size: 20 })}</span>
      <div class="callout-body">
        ${title ? html`<strong class="callout-title">${title}</strong>` : ''}
        ${text ? html`<div class="callout-text">${text}</div>` : ''}
      </div>
      ${action ? html`<div class="callout-action">${action}</div>` : ''}
    </div>`;
}

export function skeletonLines(n = 3) {
  return html`${Array.from({ length: n }, (_, i) => html`<div class="skel skel-line" style="width:${[92, 76, 64, 84, 58][i % 5]}%"></div>`)}`;
}

export function skeletonCards(n = 3, cls = '') {
  return html`${Array.from({ length: n }, () => html`
    <div class="card card-pad skel-card ${cls}">
      <div class="skel skel-thumb"></div>
      <div class="skel-stack">${skeletonLines(3)}</div>
    </div>`)}`;
}

export function errorState(err, onRetryLabel = 'Tekrar dene') {
  const network = err && err.status === 0;
  return html`
    <div class="empty">
      <div class="empty-art is-danger" aria-hidden="true">${icon(network ? 'wifiOff' : 'alert', { size: 30 })}</div>
      <h3 class="empty-title">${network ? 'Sunucuya ulaşılamadı' : 'Yüklenemedi'}</h3>
      <p class="empty-text">${(err && err.message) || 'Bilinmeyen bir hata oluştu.'}</p>
      <button type="button" class="btn" data-action="retry">${icon('refresh', { size: 18 })}<span>${onRetryLabel}</span></button>
    </div>`;
}

/** Platform rozeti (renkli nokta + ad). */
export function platformBadge(p, { compact = false } = {}) {
  return html`<span class="pbadge pbadge-${p}"><i class="pdot pdot-${p}" aria-hidden="true"></i>${compact ? '' : platformName(p)}</span>`;
}

const PUB = {
  none: { label: 'Taslak', tone: 'neutral', icon: '' },
  bekliyor: { label: 'Bekliyor', tone: 'neutral', icon: 'clock' },
  calisiyor: { label: 'Çalışıyor', tone: 'info', icon: '' },
  onay_bekliyor: { label: 'Onay bekliyor', tone: 'warning', icon: 'hand' },
  yayinda: { label: 'Yayında', tone: 'success', icon: 'check' },
  hata: { label: 'Hata', tone: 'danger', icon: 'alert' },
  iptal: { label: 'İptal', tone: 'neutral', icon: 'x' },
};
export const pubInfo = (status) => PUB[status] || PUB.none;

/** Yayın durumu çipi: [● Sahibinden · Yayında] */
export function pubChip(platform, pub, { withName = true } = {}) {
  const info = pubInfo(pub && pub.status);
  return html`
    <span class="chip chip-${info.tone}" title="${platformName(platform)}${pub && pub.message ? `: ${pub.message}` : ''}">
      ${withName ? html`<i class="pdot pdot-${platform}" aria-hidden="true"></i><span class="chip-name">${platformName(platform)}</span><span class="chip-sep" aria-hidden="true">·</span>` : html`<i class="pdot pdot-${platform}" aria-hidden="true"></i><span class="sr-only">${platformName(platform)}: </span>`}
      ${pub && pub.status === 'calisiyor' ? spinner(10) : info.icon ? icon(info.icon, { size: 13, strokeWidth: 2.2 }) : ''}
      <span>${info.label}</span>
    </span>`;
}

/** Puan halkası (0–100). */
export function scoreRing(score, { size = 44, label = 'Puan', tone } = {}) {
  const s = Math.max(0, Math.min(100, Math.round(Number(score) || 0)));
  const t = tone || (s >= 65 ? 'good' : s >= 40 ? 'ok' : 'weak');
  return html`
    <span class="ring ring-${t}" style="width:${size}px;height:${size}px" role="img" aria-label="${label} ${s}/100">
      <svg viewBox="0 0 36 36" aria-hidden="true">
        <circle class="ring-track" cx="18" cy="18" r="15.5" />
        <circle class="ring-fill" cx="18" cy="18" r="15.5" pathLength="100" stroke-dasharray="${s} 100" />
      </svg>
      <b>${s}</b>
    </span>`;
}

/** Başlık puanı rozeti. */
export function scoreBadge(score, { label = 'Puan' } = {}) {
  const s = Math.round(Number(score) || 0);
  const t = s >= 80 ? 'good' : s >= 60 ? 'ok' : 'weak';
  return html`<span class="score score-${t}" title="${label}: ${s}/100" aria-label="${label} ${s}/100">${s}</span>`;
}

const RISK = { yuksek: { label: 'Yüksek risk', tone: 'danger' }, orta: { label: 'Orta risk', tone: 'orange' }, dusuk: { label: 'Düşük risk', tone: 'yellow' } };
export function riskChip(flag) {
  const r = RISK[flag.level] || RISK.orta;
  return html`<span class="chip chip-${r.tone} chip-wrap" title="${r.label}">${icon('alert', { size: 13, strokeWidth: 2.2 })}<span><span class="sr-only">${r.label}: </span>${flag.text}</span></span>`;
}

// ------------------------------------------------------------------ fotoğraf görüntüleyici

export function openLightbox(urls, start = 0, { alt = 'Fotoğraf' } = {}) {
  let i = start;
  const sheet = openSheet({
    className: 'lightbox',
    size: 'full',
    body: html`
      <figure class="lb-figure">
        <img class="lb-img" alt="" />
        <figcaption class="lb-cap"></figcaption>
      </figure>
      <button type="button" class="lb-nav lb-prev" aria-label="Önceki fotoğraf">${icon('chevronLeft', { size: 28 })}</button>
      <button type="button" class="lb-nav lb-next" aria-label="Sonraki fotoğraf">${icon('chevronRight', { size: 28 })}</button>
      <button type="button" class="lb-close" data-close aria-label="Kapat">${icon('x', { size: 24 })}</button>`,
  });
  const img = $('.lb-img', sheet.root);
  const cap = $('.lb-cap', sheet.root);
  const show = () => {
    img.src = urls[i];
    img.alt = `${alt} ${i + 1}`;
    cap.textContent = urls.length > 1 ? `${i + 1} / ${urls.length}` : '';
    $('.lb-prev', sheet.root).hidden = urls.length < 2;
    $('.lb-next', sheet.root).hidden = urls.length < 2;
  };
  const go = (d) => {
    i = (i + d + urls.length) % urls.length;
    show();
  };
  $('.lb-prev', sheet.root).addEventListener('click', () => go(-1));
  $('.lb-next', sheet.root).addEventListener('click', () => go(1));
  const onKey = (e) => {
    if (e.key === 'ArrowLeft') go(-1);
    if (e.key === 'ArrowRight') go(1);
  };
  document.addEventListener('keydown', onKey);
  sheet.closed.then(() => document.removeEventListener('keydown', onKey));
  let x0 = null;
  img.addEventListener('touchstart', (e) => (x0 = e.touches[0].clientX), { passive: true });
  img.addEventListener('touchend', (e) => {
    if (x0 == null) return;
    const dx = e.changedTouches[0].clientX - x0;
    if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
    x0 = null;
  });
  show();
  return sheet;
}

// ------------------------------------------------------------------ grafik ipucu (tooltip)

let tipEl = null;
function tip() {
  if (!tipEl) {
    tipEl = document.createElement('div');
    tipEl.className = 'chart-tip';
    tipEl.setAttribute('role', 'tooltip');
    tipEl.hidden = true;
    document.body.appendChild(tipEl);
  }
  return tipEl;
}

/** [data-tip-value] / [data-tip-label] taşıyan öğeler için ipucu davranışı ekler. */
export function bindChartTips(root) {
  const showFor = (target) => {
    const t = tip();
    t.replaceChildren();
    const v = document.createElement('strong');
    v.textContent = target.dataset.tipValue || '';
    const l = document.createElement('span');
    l.textContent = target.dataset.tipLabel || '';
    t.append(v, l);
    t.hidden = false;
    const r = target.getBoundingClientRect();
    const tw = t.offsetWidth;
    const th = t.offsetHeight;
    let x = r.left + r.width / 2 - tw / 2;
    x = Math.max(8, Math.min(window.innerWidth - tw - 8, x));
    let y = r.top - th - 8;
    if (y < 8) y = r.bottom + 8;
    t.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    target.classList.add('is-hot');
  };
  const hide = (target) => {
    tip().hidden = true;
    if (target) target.classList.remove('is-hot');
  };
  root.addEventListener('pointerover', (e) => {
    const t = e.target.closest('[data-tip-value]');
    if (t && root.contains(t)) showFor(t);
  });
  root.addEventListener('pointerout', (e) => {
    const t = e.target.closest('[data-tip-value]');
    if (t) hide(t);
  });
  root.addEventListener('focusin', (e) => {
    const t = e.target.closest('[data-tip-value]');
    if (t) showFor(t);
  });
  root.addEventListener('focusout', (e) => {
    const t = e.target.closest('[data-tip-value]');
    if (t) hide(t);
  });
}

export function hideChartTip() {
  if (tipEl) tipEl.hidden = true;
}

// ------------------------------------------------------------------ küçük yardımcılar

export function priceLine(v, currency) {
  return fmtPrice(v, currency);
}
