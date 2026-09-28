// AutoSell web paneli — giriş noktası: tema, oturum, uygulama kabuğu, yönlendirici ve iş yoklaması.
import { api, onAuthRequired, onBlocked, onConnection } from './api.js';
import { html, el, $, $$, store, refreshTimes } from './util.js';
import { icon } from './icons.js';
import { toast, setBusy } from './ui.js';
import { startRouter } from './router.js';
import { startJobs, stopJobs, openJobsDrawer, handleJobClicks } from './jobs.js';
import { getStatus, onStatus, invalidateStatus } from './state.js';

const root = document.getElementById('app');

// ------------------------------------------------------------------ tema

const THEME_KEY = 'theme';
const darkMq = window.matchMedia('(prefers-color-scheme: dark)');

export function themePref() {
  const v = store.get(THEME_KEY, 'system');
  return v === 'light' || v === 'dark' ? v : 'system';
}

export function effectiveTheme() {
  const pref = themePref();
  return pref === 'system' ? (darkMq.matches ? 'dark' : 'light') : pref;
}

export function applyTheme() {
  const eff = effectiveTheme();
  document.documentElement.dataset.theme = eff;
  document.documentElement.dataset.themePref = themePref();
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', eff === 'dark' ? '#0f1115' : '#f4f5f8');
  for (const b of $$('[data-theme-toggle]')) {
    const next = eff === 'dark' ? 'Açık temaya geç' : 'Koyu temaya geç';
    b.setAttribute('aria-label', next);
    b.setAttribute('title', next);
    const ic = b.querySelector('.theme-ic');
    if (ic) ic.innerHTML = icon(eff === 'dark' ? 'sun' : 'moon', { size: 20 }).s;
    const lb = b.querySelector('.theme-label');
    if (lb) lb.textContent = eff === 'dark' ? 'Açık tema' : 'Koyu tema';
  }
}

export function setThemePref(pref) {
  store.set(THEME_KEY, pref);
  applyTheme();
  document.dispatchEvent(new CustomEvent('autosell:theme'));
}

darkMq.addEventListener('change', () => {
  if (themePref() === 'system') applyTheme();
});

function toggleTheme() {
  setThemePref(effectiveTheme() === 'dark' ? 'light' : 'dark');
}

// ------------------------------------------------------------------ marka

export const logo = (size = 32) => html`
  <svg class="logo" width="${size}" height="${size}" viewBox="0 0 64 64" aria-hidden="true">
    <defs><linearGradient id="lg-${size}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#7472f7"/><stop offset="1" stop-color="#4338ca"/></linearGradient></defs>
    <rect width="64" height="64" rx="16" fill="url(#lg-${size})"/>
    <path d="M16 30.5V19.2c0-1.8 1.4-3.2 3.2-3.2h11.3c.9 0 1.7.3 2.3.9l13.9 13.9c1.2 1.2 1.2 3.3 0 4.5L35.4 46.6c-1.2 1.2-3.3 1.2-4.5 0L16.9 32.8c-.6-.6-.9-1.4-.9-2.3Z" fill="#fff"/>
    <circle cx="23.6" cy="23.6" r="3.4" fill="#5552ee"/>
    <path d="M47.5 10.5l1.5 3.9 3.9 1.5-3.9 1.5-1.5 3.9-1.5-3.9-3.9-1.5 3.9-1.5Z" fill="#fff" opacity=".95"/>
  </svg>`;

// ------------------------------------------------------------------ ekranlar: açılış, giriş, engel

function splash() {
  root.innerHTML = html`
    <div class="splash" aria-busy="true">
      ${logo(56)}
      <span class="spinner" aria-hidden="true"></span>
      <span class="sr-only">AutoSell yükleniyor…</span>
    </div>`.s;
}

function centerScreen(content) {
  root.innerHTML = html`<div class="center-screen"><div class="center-card card">${content}</div></div>`.s;
}

let appStarted = false;

function showLogin(message = '') {
  stopJobs();
  appStarted = false;
  document.title = 'Giriş · AutoSell';
  centerScreen(html`
    <form class="login" novalidate>
      <div class="login-brand">${logo(52)}<h1>AutoSell</h1><p>Devam etmek için panel şifresini girin.</p></div>
      <div class="field">
        <label class="label" for="login-pw">Panel şifresi</label>
        <div class="input-wrap">
          <input id="login-pw" class="input" type="password" name="password" autocomplete="current-password" required autofocus />
          <button type="button" class="input-btn" data-reveal aria-label="Şifreyi göster" aria-pressed="false">${icon('eye', { size: 18 })}</button>
        </div>
        <p class="field-error" id="login-err" role="alert" ${message ? '' : 'hidden'}>${message}</p>
      </div>
      <button class="btn btn-primary btn-lg btn-block" type="submit">${icon('lock', { size: 18 })}<span>Giriş yap</span></button>
      <p class="hint center">Şifreyi AutoSell'in çalıştığı bilgisayarda Ayarlar › Panel Güvenliği bölümünden belirleyebilirsiniz.</p>
    </form>`);
  const form = $('form', root);
  const input = $('#login-pw', root);
  const err = $('#login-err', root);
  $('[data-reveal]', root).addEventListener('click', (e) => {
    const b = e.currentTarget;
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    b.setAttribute('aria-pressed', String(show));
    b.setAttribute('aria-label', show ? 'Şifreyi gizle' : 'Şifreyi göster');
    b.innerHTML = icon(show ? 'eyeOff' : 'eye', { size: 18 }).s;
  });
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = $('button[type="submit"]', form);
    if (!input.value) {
      err.textContent = 'Şifreyi girin.';
      err.hidden = false;
      input.focus();
      return;
    }
    setBusy(btn, true, 'Giriş yapılıyor…');
    try {
      await api.post('/api/login', { password: input.value });
      startApp();
    } catch (ex) {
      setBusy(btn, false);
      err.textContent = ex.status === 401 ? 'Şifre hatalı. Tekrar deneyin.' : ex.message;
      err.hidden = false;
      input.select();
    }
  });
  setTimeout(() => input.focus(), 50);
}

function showBlocked(message) {
  stopJobs();
  appStarted = false;
  document.title = 'Erişim kapalı · AutoSell';
  centerScreen(html`
    <div class="blocked">
      <div class="empty-art is-warning" aria-hidden="true">${icon('lock', { size: 30 })}</div>
      <h1>Ağdan erişim kapalı</h1>
      <p>${message || 'Panele ağdan erişmek için Ayarlar’dan şifre belirleyin.'}</p>
      <ol class="steps">
        <li>AutoSell'in çalıştığı bilgisayarda paneli açın (<code>http://127.0.0.1:8000</code>).</li>
        <li><strong>Ayarlar › Panel Güvenliği</strong> bölümünden bir şifre belirleyin.</li>
        <li>Bu sayfayı yenileyip şifrenizle giriş yapın.</li>
      </ol>
      <button type="button" class="btn btn-primary" data-retry>${icon('refresh', { size: 18 })}<span>Yeniden dene</span></button>
    </div>`);
  $('[data-retry]', root).addEventListener('click', () => boot());
}

function showUnreachable(message) {
  centerScreen(html`
    <div class="blocked">
      <div class="empty-art is-danger" aria-hidden="true">${icon('wifiOff', { size: 30 })}</div>
      <h1>Sunucuya ulaşılamadı</h1>
      <p>${message}</p>
      <p class="muted small">AutoSell'in çalıştığından ve aynı ağa bağlı olduğunuzdan emin olun.</p>
      <button type="button" class="btn btn-primary" data-retry>${icon('refresh', { size: 18 })}<span>Yeniden dene</span></button>
    </div>`);
  $('[data-retry]', root).addEventListener('click', () => boot());
}

// ------------------------------------------------------------------ kabuk

const NAV = [
  { key: 'panel', href: '#/', label: 'Panel', icon: 'home' },
  { key: 'ilanlar', href: '#/ilanlar', label: 'İlanlarım', icon: 'tag' },
  { key: 'firsatlar', href: '#/firsatlar', label: 'Fırsatlar', icon: 'target' },
  { key: 'takip', href: '#/takip', label: 'Takip Listeleri', icon: 'eye' },
  { key: 'arastir', href: '#/arastir', label: 'Fiyat Araştırması', icon: 'chart' },
  { key: 'ayarlar', href: '#/ayarlar', label: 'Ayarlar', icon: 'settings' },
];

function shellMarkup() {
  return html`
    <a class="skip-link" href="#view">İçeriğe geç</a>
    <div class="app-shell">
      <aside class="sidebar" aria-label="Ana menü">
        <a class="brand" href="#/" aria-label="AutoSell ana sayfa">${logo(34)}<span class="brand-name">AutoSell</span></a>
        <a class="btn btn-primary btn-block sidebar-cta" href="#/yeni" data-nav-cta>${icon('plus', { size: 18, strokeWidth: 2.2 })}<span>Yeni İlan</span></a>
        <nav class="side-nav">
          ${NAV.map((n) => html`<a class="side-link" data-nav="${n.key}" href="${n.href}">${icon(n.icon, { size: 20 })}<span>${n.label}</span></a>`)}
        </nav>
        <div class="side-foot">
          <button type="button" class="side-link" data-jobs-button aria-label="İşler">${icon('activity', { size: 20 })}<span>İşler</span><span class="badge" data-jobs-badge hidden></span></button>
          <button type="button" class="side-link" data-theme-toggle><span class="theme-ic">${icon('moon', { size: 20 })}</span><span class="theme-label">Koyu tema</span></button>
          <a class="side-status" href="#/ayarlar?b=ai" data-ai-status><span class="status-dot" aria-hidden="true"></span><span class="side-status-text">Durum yükleniyor…</span></a>
        </div>
      </aside>
      <div class="main">
        <header class="topbar">
          <a class="topbar-back" href="#/" hidden>${icon('chevronLeft', { size: 24 })}<span class="topbar-back-label">Geri</span></a>
          <a class="topbar-brand" href="#/" aria-label="AutoSell ana sayfa">${logo(28)}<span>AutoSell</span></a>
          <span class="topbar-title" aria-hidden="true"></span>
          <div class="topbar-actions">
            <button type="button" class="btn btn-ghost btn-icon topbar-jobs" data-jobs-button aria-label="İşler">${icon('activity', { size: 22 })}<span class="badge" data-jobs-badge hidden></span></button>
            <button type="button" class="btn btn-ghost btn-icon" data-theme-toggle><span class="theme-ic">${icon('moon', { size: 22 })}</span></button>
          </div>
        </header>
        <div class="conn-banner" id="conn-banner" hidden role="status">
          ${icon('wifiOff', { size: 18 })}<span>Sunucuya ulaşılamıyor. AutoSell kapalı olabilir; yeniden deneniyor…</span>
        </div>
        <div class="banners" id="banners" aria-live="polite"></div>
        <main id="view" class="view" tabindex="-1"></main>
      </div>
      <nav class="tabbar" aria-label="Alt menü">
        <a class="tab-link" data-mnav="panel" href="#/">${icon('home', { size: 24 })}<span>Panel</span></a>
        <a class="tab-link" data-mnav="ilanlar" href="#/ilanlar">${icon('tag', { size: 24 })}<span>İlanlarım</span></a>
        <a class="tab-link tab-cta" data-mnav="yeni" href="#/yeni"><span class="tab-cta-btn">${icon('plus', { size: 26, strokeWidth: 2.3 })}</span><span>Yeni İlan</span></a>
        <a class="tab-link" data-mnav="firsatlar" href="#/firsatlar">${icon('target', { size: 24 })}<span>Fırsatlar</span></a>
        <a class="tab-link" data-mnav="ayarlar" href="#/ayarlar">${icon('settings', { size: 24 })}<span>Ayarlar</span></a>
      </nav>
    </div>`;
}

let titleObserver = null;

const shell = {
  update({ nav, mobileNav, title, back, backLabel }) {
    for (const a of $$('[data-nav]')) {
      if (a.dataset.nav === nav) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    }
    const cta = $('[data-nav-cta]');
    if (cta) cta.classList.toggle('is-current', nav === 'yeni');
    for (const a of $$('[data-mnav]')) {
      if (a.dataset.mnav === (mobileNav || nav)) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    }
    const bar = $('.topbar');
    if (!bar) return;
    if (title !== undefined) $('.topbar-title', bar).textContent = title || '';
    if (back !== undefined) {
      const b = $('.topbar-back', bar);
      b.hidden = !back;
      if (back) {
        b.href = back;
        b.setAttribute('aria-label', `${backLabel || 'Geri'} sayfasına dön`);
        $('.topbar-back-label', b).textContent = backLabel || 'Geri';
      }
      $('.topbar-brand', bar).hidden = !!back;
      bar.classList.toggle('has-back', !!back);
    }
  },
  afterRender(view) {
    const bar = $('.topbar');
    if (!bar) return;
    bar.classList.remove('title-visible');
    if (titleObserver) titleObserver.disconnect();
    const h = $('.page-title', view);
    if (!h || !('IntersectionObserver' in window)) {
      bar.classList.add('title-visible');
      return;
    }
    titleObserver = new IntersectionObserver(
      ([entry]) => bar.classList.toggle('title-visible', !entry.isIntersecting && entry.boundingClientRect.top < 80),
      { rootMargin: '-64px 0px 0px 0px', threshold: 0 },
    );
    titleObserver.observe(h);
  },
};

function renderAiStatus(s) {
  const a = $('[data-ai-status]');
  if (!a || !s) return;
  const ok = s.ai && s.ai.configured;
  a.classList.toggle('is-ok', !!ok);
  a.classList.toggle('is-warn', !ok);
  $('.side-status-text', a).textContent = ok ? `Yapay zekâ hazır · v${s.version}` : 'Yapay zekâ ayarlı değil';
  a.title = ok ? s.ai.description || '' : 'Ayarlar › Yapay Zekâ bölümünden bir sağlayıcı tanımlayın';
}

function startApp() {
  appStarted = true;
  root.innerHTML = shellMarkup().s;
  applyTheme();
  const view = $('#view');
  startRouter({ shell, view });
  startJobs({ bannerRoot: $('#banners') });
  getStatus({ force: true }).catch(() => {});
}

// ------------------------------------------------------------------ genel olaylar

document.addEventListener('click', (e) => {
  if (e.target.closest('[data-jobs-button]')) {
    openJobsDrawer();
    return;
  }
  if (e.target.closest('[data-theme-toggle]')) {
    toggleTheme();
    return;
  }
  if (e.target.closest('#banners')) handleJobClicks(e);
});

window.addEventListener('scroll', () => {
  const bar = document.querySelector('.topbar');
  if (bar) bar.classList.toggle('is-scrolled', window.scrollY > 4);
}, { passive: true });

onStatus(renderAiStatus);
setInterval(() => {
  if (!appStarted || document.hidden) return;
  refreshTimes();
}, 30000);
setInterval(() => {
  if (!appStarted || document.hidden) return;
  invalidateStatus();
  getStatus().catch(() => {});
}, 60000);

onAuthRequired(() => {
  if (appStarted) toast.info('Oturumunuzun süresi doldu. Lütfen yeniden giriş yapın.');
  showLogin();
});
onBlocked((err) => showBlocked(err.message));
onConnection((ok) => {
  const b = document.getElementById('conn-banner');
  if (b) b.hidden = ok;
});

async function boot() {
  applyTheme();
  splash();
  let auth;
  try {
    auth = await api('/api/auth');
  } catch (e) {
    if (e.status === 403) return showBlocked(e.message);
    if (e.status === 0) return showUnreachable(e.message);
    auth = { required: false, ok: true };
  }
  if (auth.required && !auth.ok) return showLogin();
  startApp();
}

boot();
