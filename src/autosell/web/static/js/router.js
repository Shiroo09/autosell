// Karma (#) tabanlı yönlendirici: görünümleri tembel yükler, kaydedilmemiş değişikliklerde uyarır.
import { html, setHTML, refreshTimes } from './util.js';
import { choiceDialog, hideChartTip } from './ui.js';
import { icon } from './icons.js';

export const ROUTES = [
  { name: 'dashboard', re: /^\/$/, title: 'Panel', nav: 'panel', load: () => import('./views/dashboard.js') },
  { name: 'new', re: /^\/yeni$/, title: 'Yeni İlan', nav: 'yeni', load: () => import('./views/new.js') },
  { name: 'drafts', re: /^\/ilanlar$/, title: 'İlanlarım', nav: 'ilanlar', load: () => import('./views/drafts.js') },
  { name: 'editor', re: /^\/ilan\/([^/]+)$/, title: 'İlan', nav: 'ilanlar', back: '#/ilanlar', backLabel: 'İlanlarım', load: () => import('./views/editor.js') },
  { name: 'deals', re: /^\/firsatlar$/, title: 'Fırsatlar', nav: 'firsatlar', load: () => import('./views/deals.js') },
  { name: 'deal', re: /^\/firsat\/(\d+)$/, title: 'Fırsat', nav: 'firsatlar', back: '#/firsatlar', backLabel: 'Fırsatlar', load: () => import('./views/deal.js') },
  { name: 'watches', re: /^\/takip$/, title: 'Takip Listeleri', nav: 'takip', mobileNav: 'firsatlar', back: '#/firsatlar', backLabel: 'Fırsatlar', mobileOnlyBack: true, load: () => import('./views/watches.js') },
  { name: 'research', re: /^\/arastir$/, title: 'Fiyat Araştırması', nav: 'arastir', mobileNav: 'firsatlar', back: '#/firsatlar', backLabel: 'Fırsatlar', mobileOnlyBack: true, load: () => import('./views/research.js') },
  { name: 'settings', re: /^\/ayarlar$/, title: 'Ayarlar', nav: 'ayarlar', load: () => import('./views/settings.js') },
];

export function parseHash(hash = location.hash) {
  const h = String(hash || '').replace(/^#/, '') || '/';
  const [path, qs = ''] = h.split('?');
  return { path: path || '/', query: new URLSearchParams(qs) };
}

function match(path) {
  for (const r of ROUTES) {
    const m = path.match(r.re);
    if (m) return { route: r, params: m.slice(1).map((x) => decodeURIComponent(x)) };
  }
  return null;
}

let shell = null;
let viewEl = null;
let current = null; // { route, ctrl, scope, hash }
let renderToken = 0;
let bypass = false;
let started = false;

/** Görünüm yaşam döngüsü: temizlik işlevleri, zamanlayıcılar, iptal sinyali. */
function createScope(token) {
  const cleanups = new Set();
  const ac = new AbortController();
  const scope = {
    signal: ac.signal,
    alive: () => token === renderToken && !ac.signal.aborted,
    cleanup(fn) {
      cleanups.add(fn);
      return () => cleanups.delete(fn);
    },
    /** Görünür olduğunda düzenli çalışan işlev; sekme gizliyken durur. */
    interval(fn, ms, { immediate = false } = {}) {
      let t = null;
      let stopped = false;
      const tick = async () => {
        if (stopped) return;
        if (!document.hidden) {
          try {
            await fn();
          } catch {
            /* görünüm kendi hatasını gösterir */
          }
        }
        if (!stopped) t = setTimeout(tick, ms);
      };
      const onVis = () => {
        if (!document.hidden && !stopped) {
          clearTimeout(t);
          tick();
        }
      };
      document.addEventListener('visibilitychange', onVis);
      if (immediate) tick();
      else t = setTimeout(tick, ms);
      const stop = () => {
        stopped = true;
        clearTimeout(t);
        document.removeEventListener('visibilitychange', onVis);
      };
      cleanups.add(stop);
      return stop;
    },
    on(target, type, fn, opts) {
      target.addEventListener(type, fn, opts);
      cleanups.add(() => target.removeEventListener(type, fn, opts));
    },
    destroy() {
      ac.abort();
      for (const fn of cleanups) {
        try {
          fn();
        } catch {
          /* yok say */
        }
      }
      cleanups.clear();
    },
  };
  return scope;
}

export function currentRoute() {
  return current ? current.route : null;
}

/** Programatik gezinme. force: kaydedilmemiş değişiklik uyarısını atla. */
export function navigate(to, { replace = false, force = false } = {}) {
  const target = to.startsWith('#') ? to : `#${to}`;
  if (force) bypass = true;
  if (replace) {
    history.replaceState(null, '', target);
    render();
    return;
  }
  if (location.hash === target) {
    render();
    return;
  }
  location.hash = target;
}

/** Aynı sayfada adres çubuğundaki sorgu parametrelerini sessizce günceller. */
export function replaceQuery(params) {
  const { path } = parseHash();
  const qs = new URLSearchParams(params);
  for (const [k, v] of [...qs]) if (v === '' || v == null) qs.delete(k);
  const s = qs.toString();
  const hash = `#${path}${s ? `?${s}` : ''}`;
  history.replaceState(null, '', hash);
  if (current) current.hash = hash;
}

async function guardLeave() {
  const ctrl = current && current.ctrl;
  if (!ctrl || typeof ctrl.isDirty !== 'function' || !ctrl.isDirty()) return true;
  const choices = [{ value: 'stay', label: 'Sayfada kal' }, { value: 'discard', label: 'Kaydetmeden çık', kind: 'danger' }];
  if (typeof ctrl.save === 'function') choices.push({ value: 'save', label: 'Kaydet ve çık', kind: 'primary' });
  const choice = await choiceDialog({
    title: 'Kaydedilmemiş değişiklikler',
    message: ctrl.leaveMessage || 'Bu sayfada kaydetmediğiniz değişiklikler var. Çıkarsanız kaybolacaklar.',
    icon: 'alert',
    choices,
  });
  if (choice === 'save') return (await ctrl.save()) !== false;
  return choice === 'discard';
}

async function onHashChange() {
  const target = location.hash || '#/';
  if (current && target === current.hash) return;
  if (bypass) {
    bypass = false;
    render();
    return;
  }
  if (current && current.ctrl && typeof current.ctrl.isDirty === 'function' && current.ctrl.isDirty()) {
    history.replaceState(null, '', current.hash);
    const ok = await guardLeave();
    if (!ok) return;
    bypass = true;
    location.hash = target;
    return;
  }
  render();
}

function viewLoading() {
  return html`<div class="view-loading" aria-busy="true"><span class="spinner" aria-hidden="true"></span><span class="sr-only">Yükleniyor…</span></div>`;
}

async function render() {
  const token = ++renderToken;
  const { path, query } = parseHash();
  const found = match(path);
  hideChartTip();
  if (current) {
    try {
      current.ctrl && current.ctrl.destroy && current.ctrl.destroy();
    } catch {
      /* yok say */
    }
    current.scope.destroy();
  }
  const scope = createScope(token);
  current = { route: found ? found.route : null, ctrl: null, scope, hash: location.hash || '#/' };
  if (!found) {
    shell.update({ nav: '', title: 'Sayfa bulunamadı' });
    setHTML(viewEl, html`
      <div class="empty">
        <div class="empty-art" aria-hidden="true">${icon('search', { size: 30 })}</div>
        <h1 class="empty-title">Sayfa bulunamadı</h1>
        <p class="empty-text">Aradığınız sayfa taşınmış ya da hiç var olmamış olabilir.</p>
        <a class="btn btn-primary" href="#/">Panele dön</a>
      </div>`);
    return;
  }
  const { route, params } = found;
  shell.update({ nav: route.nav, mobileNav: route.mobileNav || route.nav, title: route.title, back: route.back, backLabel: route.backLabel, mobileOnlyBack: route.mobileOnlyBack });
  document.title = `${route.title} · AutoSell`;
  setHTML(viewEl, viewLoading());
  window.scrollTo(0, 0);
  let mod;
  try {
    mod = await route.load();
  } catch (e) {
    if (token !== renderToken) return;
    setHTML(viewEl, html`
      <div class="empty">
        <div class="empty-art is-danger" aria-hidden="true">${icon('alert', { size: 30 })}</div>
        <h1 class="empty-title">Sayfa yüklenemedi</h1>
        <p class="empty-text">Bağlantınızı kontrol edip sayfayı yenileyin.</p>
        <button class="btn" type="button" onclick="location.reload()">Yenile</button>
      </div>`);
    return;
  }
  if (token !== renderToken) return;
  viewEl.replaceChildren();
  const ctx = {
    params,
    query,
    scope,
    signal: scope.signal,
    alive: scope.alive,
    setTitle(title) {
      if (!scope.alive()) return;
      shell.update({ title });
      document.title = `${title} · AutoSell`;
    },
  };
  try {
    current.ctrl = (await mod.mount(viewEl, ctx)) || null;
  } catch (e) {
    if (e && e.name === 'AbortError') return;
    console.error(e);
  }
  if (token !== renderToken) {
    if (current && current.ctrl && current.ctrl.destroy) current.ctrl.destroy();
    return;
  }
  refreshTimes(viewEl);
  shell.afterRender && shell.afterRender(viewEl);
}

export function startRouter({ shell: s, view }) {
  shell = s;
  viewEl = view;
  if (!started) {
    started = true;
    window.addEventListener('hashchange', onHashChange);
    window.addEventListener('beforeunload', (e) => {
      const ctrl = current && current.ctrl;
      if (ctrl && typeof ctrl.isDirty === 'function' && ctrl.isDirty()) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }
  render();
}

export function rerender() {
  render();
}
