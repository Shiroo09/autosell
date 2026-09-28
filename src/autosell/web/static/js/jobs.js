// Arka plan işleri: genel yoklama, canlı iş kartları, iş çekmecesi ve kullanıcı onayı pencereleri.
import { api, enc } from './api.js';
import { html, el, $, $$, fmtRel, timeAgo, fmtPrice, safeUrl, platformName, refreshTimes } from './util.js';
import { icon } from './icons.js';
import { toast, openSheet, setBusy, spinner, showError } from './ui.js';

const ACTIVE = new Set(['queued', 'running', 'waiting']);
export const isActive = (job) => !!job && ACTIVE.has(job.status);

export const KIND = {
  generate: { label: 'İlan oluşturma', icon: 'sparkles' },
  publish: { label: 'Yayınlama', icon: 'upload' },
  login: { label: 'Giriş', icon: 'key' },
  scan: { label: 'Tarama', icon: 'target' },
  research: { label: 'Fiyat araştırması', icon: 'chart' },
};
export const kindInfo = (k) => KIND[k] || { label: 'İş', icon: 'activity' };

export const STATUS = {
  queued: { label: 'Sırada', tone: 'neutral' },
  running: { label: 'Çalışıyor', tone: 'info' },
  waiting: { label: 'Sizi bekliyor', tone: 'warning' },
  done: { label: 'Tamamlandı', tone: 'success' },
  error: { label: 'Hata', tone: 'danger' },
  cancelled: { label: 'İptal edildi', tone: 'neutral' },
};
export const statusInfo = (s) => STATUS[s] || { label: s || '—', tone: 'neutral' };

export function statusChip(job) {
  const info = statusInfo(job.status);
  const lead = job.status === 'running' ? spinner(10)
    : job.status === 'done' ? icon('check', { size: 13, strokeWidth: 2.4 })
      : job.status === 'error' ? icon('alert', { size: 13, strokeWidth: 2.2 })
        : job.status === 'waiting' ? icon('hand', { size: 13 })
          : job.status === 'queued' ? icon('clock', { size: 13 }) : '';
  return html`<span class="chip chip-${info.tone}">${lead}<span>${info.label}</span></span>`;
}

/** Teknik hata metnini kullanıcı diline çevirir. */
export function friendlyError(msg = '') {
  const text = String(msg || '');
  const first = text.split('\n')[0].trim();
  if (/net::ERR_(TUNNEL_CONNECTION_FAILED|NAME_NOT_RESOLVED|INTERNET_DISCONNECTED|CONNECTION_\w+|PROXY_\w+|ADDRESS_UNREACHABLE|TIMED_OUT|NETWORK_CHANGED)/.test(text)) {
    return 'Siteye bağlanılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.';
  }
  if (/Executable doesn't exist|playwright install/i.test(text)) {
    return 'Tarayıcı bulunamadı. Kurulumda "playwright install chromium" komutunu çalıştırın ya da Ayarlar › Tarayıcı bölümünden kurulu bir tarayıcı seçin.';
  }
  if (/Missing X server|\$DISPLAY|headed browser|without a display/i.test(text)) {
    return 'Tarayıcı penceresi açılamadı (ekran bulunamadı). Ayarlar › Tarayıcı bölümünden "Görünmez mod"u açabilirsiniz.';
  }
  if (/Target (page, context or browser|closed)|Browser has been closed|browser.*closed/i.test(text)) {
    return 'Tarayıcı penceresi kapatıldı. İşi yeniden başlatın.';
  }
  if (/Timeout \d+ms exceeded/i.test(first)) return 'Sayfa zamanında yanıt vermedi (zaman aşımı). Tekrar deneyin.';
  return first.length > 240 ? `${first.slice(0, 237)}…` : first || 'Bilinmeyen hata.';
}

/** İş bitince tek satırlık özet. */
export function jobSummary(job) {
  if (!job) return '';
  if (job.status === 'error') return friendlyError(job.error);
  if (job.status === 'cancelled') return job.error || 'İş iptal edildi.';
  if (job.status !== 'done') return '';
  const r = job.result || {};
  switch (job.kind) {
    case 'generate':
      return 'İlan metinleri hazır.';
    case 'publish':
      return `${r.message || 'İlan oluşturuldu.'}${r.listing_no ? ` İlan no: ${r.listing_no}` : ''}`;
    case 'research':
      return r.matched ? `${r.matched} benzer ilan bulundu · medyan ${fmtPrice(r.estimate && r.estimate.median)}` : 'Yeterli benzer ilan bulunamadı.';
    case 'scan':
      return r.message ? `Tarama bitti: ${r.message}` : 'Tarama bitti.';
    case 'login':
      return 'Oturum açıldı ve kaydedildi.';
    default:
      return 'Tamamlandı.';
  }
}

export function jobLink(job) {
  if (!job) return null;
  if (job.draft_id) return { href: `#/ilan/${enc(job.draft_id)}`, label: 'İlana git' };
  if (job.kind === 'research') return { href: `#/arastir?is=${enc(job.id)}`, label: 'Sonuçlar' };
  if (job.kind === 'scan') return { href: job.watch_id ? `#/firsatlar?watch=${job.watch_id}` : '#/firsatlar', label: 'Fırsatlar' };
  return null;
}

// ------------------------------------------------------------------ genel durum

const state = {
  active: new Map(),
  listeners: new Set(),
  timer: null,
  watched: new Map(), // iş id → izleyen kart sayısı (bitiş bildirimi bastırmak için)
  promptSheets: new Map(), // iş id → açık onay penceresi
  dismissed: new Set(), // kapatılan onay istemleri (iş id|mesaj)
  started: false,
  bannerRoot: null,
  badgeEls: [],
};

export function activeJobs() {
  return [...state.active.values()];
}

/** Aktif iş listesi değişince çağrılır. */
export function onJobsChange(fn) {
  state.listeners.add(fn);
  fn(activeJobs());
  return () => state.listeners.delete(fn);
}

function emit() {
  const list = activeJobs();
  state.listeners.forEach((fn) => {
    try {
      fn(list);
    } catch (e) {
      console.error(e);
    }
  });
  updateBadges(list);
  renderBanners(list);
  syncPrompts(list);
}

function updateBadges(list) {
  for (const b of document.querySelectorAll('[data-jobs-badge]')) {
    const n = list.length;
    b.textContent = n ? String(n) : '';
    b.hidden = !n;
  }
  for (const btn of document.querySelectorAll('[data-jobs-button]')) {
    btn.classList.toggle('has-jobs', list.length > 0);
    btn.classList.toggle('has-waiting', list.some((j) => j.status === 'waiting'));
    btn.setAttribute('aria-label', list.length ? `İşler: ${list.length} aktif iş` : 'İşler');
  }
}

async function poll() {
  clearTimeout(state.timer);
  try {
    const jobs = await api('/api/jobs?active=1&limit=50');
    const next = new Map(jobs.map((j) => [j.id, j]));
    const gone = [...state.active.values()].filter((j) => !next.has(j.id));
    state.active = next;
    emit();
    gone.forEach((j) => finished(j));
  } catch {
    /* bağlantı durumu api.js üzerinden bildirilir */
  }
  state.timer = setTimeout(poll, document.hidden ? 15000 : 3000);
}

async function finished(old) {
  let job = null;
  try {
    job = await api(`/api/jobs/${enc(old.id)}?since=${old.log_count || 0}`);
  } catch {
    return;
  }
  dispatchFinished(job);
  if (!state.watched.get(job.id)) notifyFinished(job);
}

const finishedSeen = new Set();
/** Biten işi tek sefer duyurur (izleyici ve genel yoklama aynı işi bildirebilir). */
function dispatchFinished(job) {
  if (!job || finishedSeen.has(job.id)) return;
  finishedSeen.add(job.id);
  if (finishedSeen.size > 300) finishedSeen.delete(finishedSeen.values().next().value);
  document.dispatchEvent(new CustomEvent('autosell:job-finished', { detail: job }));
}

function notifyFinished(job) {
  const link = jobLink(job);
  const name = job.platform ? `${platformName(job.platform)} · ` : '';
  if (job.status === 'done') {
    toast.success(jobSummary(job), { title: `${name}${kindInfo(job.kind).label} tamamlandı`, action: link });
  } else if (job.status === 'error') {
    toast.error(friendlyError(job.error), { title: `${name}${kindInfo(job.kind).label} başarısız`, action: link });
  } else if (job.status === 'cancelled') {
    toast.info(job.title, { title: 'İş iptal edildi' });
  }
}

/** Yeni başlatılan bir işi hemen izlemeye alır. */
export function trackJob(job) {
  if (!job) return;
  if (isActive(job)) {
    state.active.set(job.id, job);
    emit();
  }
  clearTimeout(state.timer);
  state.timer = setTimeout(poll, 600);
}

export function refreshJobs() {
  poll();
}

export function startJobs({ bannerRoot }) {
  state.bannerRoot = bannerRoot;
  if (state.started) return;
  state.started = true;
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) poll();
  });
  poll();
}

export function stopJobs() {
  clearTimeout(state.timer);
  state.started = false;
}

// ------------------------------------------------------------------ iş işlemleri

export async function cancelJob(id, btn) {
  try {
    setBusy(btn, true, 'İptal ediliyor…');
    const r = await api.post(`/api/jobs/${enc(id)}/cancel`);
    if (!r || !r.ok) toast.info('İş zaten bitmiş.');
    else toast.info('İptal isteği gönderildi.');
  } catch (e) {
    showError(e);
  } finally {
    setBusy(btn, false);
    refreshJobs();
  }
}

export async function respondJob(id, value) {
  await api.post(`/api/jobs/${enc(id)}/respond`, { value });
  const sheet = state.promptSheets.get(id);
  if (sheet) sheet.close('answered');
  toast.success(value ? 'Onay verildi; yayınlanıyor…' : 'Yayınlama durduruldu.');
  refreshJobs();
}

// ------------------------------------------------------------------ bekleyen işler: şerit ve onay penceresi

function promptKey(job) {
  return `${job.id}|${job.prompt ? job.prompt.message : ''}`;
}

function renderBanners(list) {
  const root = state.bannerRoot;
  if (!root) return;
  const waiting = list.filter((j) => j.status === 'waiting' && j.prompt);
  const items = waiting.filter((j) => j.prompt.type === 'human' || (j.prompt.type === 'confirm' && state.dismissed.has(promptKey(j))));
  const keys = items.map((j) => promptKey(j)).join(',');
  if (root.dataset.keys === keys) return;
  root.dataset.keys = keys;
  root.replaceChildren(...items.map((j) => el(html`
    <div class="banner banner-warning" role="alert">
      <span class="banner-icon">${icon(j.prompt.type === 'human' ? 'hand' : 'bell', { size: 20 })}</span>
      <div class="banner-body">
        <strong>${j.prompt.type === 'human' ? 'Tarayıcıda işlem gerekiyor' : 'Onayınız bekleniyor'}</strong>
        <span class="banner-text">${j.title ? `${j.title}: ` : ''}${j.prompt.message}</span>
        ${j.prompt.type === 'human' ? html`<span class="banner-hint">AutoSell'in çalıştığı bilgisayardaki tarayıcı penceresinde adımı tamamlayın; algılanınca kendiliğinden devam edilecek.</span>` : ''}
      </div>
      <div class="banner-actions">
        ${j.prompt.type === 'confirm'
          ? html`<button type="button" class="btn btn-sm btn-primary" data-reopen="${j.id}">Yanıtla</button>`
          : html`<button type="button" class="btn btn-sm" data-drawer="${j.id}">Ayrıntılar</button>`}
        <button type="button" class="btn btn-sm btn-ghost" data-cancel="${j.id}">İptal</button>
      </div>
    </div>`)));
}

function syncPrompts(list) {
  const waitingConfirm = new Map(list.filter((j) => j.status === 'waiting' && j.prompt && j.prompt.type === 'confirm').map((j) => [j.id, j]));
  for (const [id, sheet] of state.promptSheets) {
    if (!waitingConfirm.has(id)) {
      sheet.close('gone');
      state.promptSheets.delete(id);
    }
  }
  for (const job of waitingConfirm.values()) {
    if (state.promptSheets.has(job.id) || state.dismissed.has(promptKey(job))) continue;
    openConfirmPrompt(job);
  }
}

export function openConfirmPrompt(job) {
  if (state.promptSheets.has(job.id)) return state.promptSheets.get(job.id);
  const key = promptKey(job);
  state.dismissed.delete(key);
  const shot = job.has_screenshot ? `/api/jobs/${enc(job.id)}/screenshot?t=${Date.now()}` : '';
  const sheet = openSheet({
    title: 'Yayın onayı',
    subtitle: job.title || '',
    icon: 'upload',
    size: 'md',
    className: 'confirm-prompt',
    body: html`
      <p class="prompt-question">${job.prompt.message}</p>
      ${shot ? html`
        <a class="prompt-shot" href="${shot}" target="_blank" rel="noopener" title="Ekran görüntüsünü büyüt">
          <img src="${shot}" alt="Tarayıcıda doldurulan formun ekran görüntüsü" loading="lazy" onerror="this.closest('.prompt-shot').remove()" />
        </a>` : ''}
      <p class="muted small">Form, AutoSell'in çalıştığı bilgisayardaki tarayıcıda dolduruldu. İsterseniz son kontrolü o pencereden yapıp yayınlamayı orada da tamamlayabilirsiniz.</p>`,
    footer: html`
      <button type="button" class="btn" data-answer="no">Hayır, yayınlama</button>
      <button type="button" class="btn btn-primary" data-answer="yes" autofocus>${icon('check', { size: 18 })}<span>Evet, yayınla</span></button>`,
    onClose(result) {
      state.promptSheets.delete(job.id);
      if (result !== 'answered' && result !== 'gone') {
        state.dismissed.add(key);
        renderBanners(activeJobs());
      }
    },
  });
  sheet.foot.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-answer]');
    if (!b) return;
    const yes = b.dataset.answer === 'yes';
    $$('button', sheet.foot).forEach((x) => (x.disabled = true));
    setBusy(b, true, yes ? 'Gönderiliyor…' : 'Durduruluyor…');
    try {
      await respondJob(job.id, yes);
    } catch (err) {
      showError(err);
      setBusy(b, false);
      $$('button', sheet.foot).forEach((x) => (x.disabled = false));
      if (err.status === 409) sheet.close('gone');
    }
  });
  state.promptSheets.set(job.id, sheet);
  return sheet;
}

/** Şerit ve çekmecedeki düğmeler için genel tıklama işleyicisi. */
export function handleJobClicks(e) {
  const reopen = e.target.closest('[data-reopen]');
  if (reopen) {
    const job = state.active.get(reopen.dataset.reopen);
    if (job) openConfirmPrompt(job);
    return true;
  }
  const cancel = e.target.closest('[data-cancel]');
  if (cancel) {
    cancelJob(cancel.dataset.cancel, cancel);
    return true;
  }
  const drawer = e.target.closest('[data-drawer]');
  if (drawer) {
    openJobsDrawer(drawer.dataset.drawer);
    return true;
  }
  return false;
}

// ------------------------------------------------------------------ tek bir işi canlı izleme

/**
 * İşi ~1,5 sn'de bir yoklar, günlükleri biriktirir.
 * @param {string} id
 * @param {(job: object|null, err?: Error) => void} onUpdate
 */
export function watchJob(id, onUpdate, { interval = 1500 } = {}) {
  let since = 0;
  let logs = [];
  let stopped = false;
  let timer = null;
  state.watched.set(id, (state.watched.get(id) || 0) + 1);
  const release = () => {
    const n = (state.watched.get(id) || 1) - 1;
    if (n <= 0) setTimeout(() => state.watched.delete(id), 5000);
    else state.watched.set(id, n);
  };
  const tick = async () => {
    if (stopped) return;
    try {
      const j = await api(`/api/jobs/${enc(id)}?since=${since}`);
      if (stopped) return;
      if (j.log_count < since) {
        // sunucu eski günlükleri kırptı: baştan al
        since = 0;
        logs = [];
        timer = setTimeout(tick, 50);
        return;
      }
      logs = logs.concat(j.logs || []);
      since = j.log_count;
      const job = { ...j, logs };
      onUpdate(job);
      if (!isActive(job)) {
        stop();
        dispatchFinished(job);
        return;
      }
    } catch (err) {
      if (stopped) return;
      if (err && err.status === 404) {
        stop();
        onUpdate(null, err);
        return;
      }
    }
    if (!stopped) timer = setTimeout(tick, document.hidden ? 5000 : interval);
  };
  const stop = () => {
    if (stopped) return;
    stopped = true;
    clearTimeout(timer);
    release();
  };
  tick();
  return { stop };
}

// ------------------------------------------------------------------ iş kartı

function logLines(logs) {
  return html`${logs.map((l) => html`<li class="log log-${l.level || 'info'}"><time>${fmtTimeOnly(l.t)}</time><span>${l.msg}</span></li>`)}`;
}

function fmtTimeOnly(iso) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '' : d.toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

/**
 * Canlı iş kartı.
 * @param {object|string} jobOrId
 * @param {{onDone?: Function, onUpdate?: Function, dismissible?: boolean, title?: string, showResult?: boolean}} opts
 */
export function jobCard(jobOrId, opts = {}) {
  const id = typeof jobOrId === 'string' ? jobOrId : jobOrId.id;
  const initial = typeof jobOrId === 'object' ? jobOrId : { id, status: 'queued', title: opts.title || 'İş', kind: '', logs: [] };
  const node = el(html`<article class="job-card card" data-job="${id}" aria-live="polite"></article>`);
  let job = initial;
  let logsOpen = false;
  let doneCalled = false;
  let queuedSince = Date.now();

  const render = () => {
    const k = kindInfo(job.kind);
    const active = isActive(job);
    const last = (job.logs || []).slice(-1)[0];
    const stuck = job.status === 'queued' && Date.now() - queuedSince > 20000;
    const tone = statusInfo(job.status).tone;
    node.className = `job-card card job-${job.status} tone-${tone}`;
    const link = jobLink(job);
    node.innerHTML = html`
      <div class="job-head">
        <span class="job-icon">${icon(k.icon, { size: 18 })}</span>
        <div class="job-titles">
          <strong class="job-title">${job.title || k.label}</strong>
          <span class="job-meta">${job.platform ? html`<i class="pdot pdot-${job.platform}"></i>${platformName(job.platform)} · ` : ''}${k.label}${job.created_at ? html` · ${timeAgo(job.created_at)}` : ''}</span>
        </div>
        ${statusChip(job)}
        ${!active && opts.dismissible !== false ? html`<button type="button" class="btn btn-ghost btn-icon btn-sm" data-dismiss aria-label="Kartı kapat">${icon('x', { size: 16 })}</button>` : ''}
      </div>
      ${active ? html`<div class="progress ${job.status === 'waiting' ? 'is-paused' : ''}" role="progressbar" aria-label="${statusInfo(job.status).label}"><span></span></div>` : ''}
      ${job.status === 'waiting' && job.prompt ? html`
        <div class="job-prompt">
          ${icon(job.prompt.type === 'human' ? 'hand' : 'bell', { size: 18 })}
          <div>
            <strong>${job.prompt.type === 'human' ? 'Tarayıcıda işlem gerekiyor' : 'Onayınız bekleniyor'}</strong>
            <p>${job.prompt.message}</p>
            ${job.prompt.type === 'confirm' ? html`
              <div class="job-prompt-actions">
                <button type="button" class="btn btn-sm" data-answer="no">Hayır</button>
                <button type="button" class="btn btn-sm btn-primary" data-answer="yes">${icon('check', { size: 16 })}<span>Evet, yayınla</span></button>
                ${job.has_screenshot ? html`<button type="button" class="btn btn-sm btn-ghost" data-reopen="${job.id}">${icon('image', { size: 16 })}<span>Ekran görüntüsü</span></button>` : ''}
              </div>` : html`<p class="muted small">AutoSell'in çalıştığı bilgisayardaki tarayıcı penceresinde tamamlayın.</p>`}
          </div>
        </div>` : ''}
      ${stuck ? html`<p class="job-note">${icon('clock', { size: 16 })}<span>İş sırada bekliyor. Aynı platformda başka bir iş sürüyor olabilir ya da tarayıcı başlatılamamış olabilir (Ayarlar › Tarayıcı). Gerekirse iptal edip yeniden deneyin.</span></p>` : ''}
      ${!active && job.status !== 'queued' ? html`
        <p class="job-result">${icon(job.status === 'done' ? 'checkCircle' : job.status === 'error' ? 'xCircle' : 'info', { size: 18 })}<span>${jobSummary(job)}</span>
          ${job.status === 'done' && job.kind === 'publish' && job.result && safeUrl(job.result.url) ? html`<a href="${safeUrl(job.result.url)}" target="_blank" rel="noopener">İlanı görüntüle ${icon('external', { size: 14 })}</a>` : ''}
        </p>` : last && active ? html`<p class="job-last">${last.msg}</p>` : ''}
      <div class="job-foot">
        ${(job.logs || []).length ? html`<button type="button" class="btn btn-ghost btn-sm" data-toggle-logs aria-expanded="${logsOpen}">${icon(logsOpen ? 'chevronUp' : 'chevronDown', { size: 16 })}<span>${logsOpen ? 'Günlüğü gizle' : `Günlük (${job.logs.length})`}</span></button>` : html`<span></span>`}
        <div class="job-foot-actions">
          ${opts.showLink && link && !active ? html`<a class="btn btn-sm" href="${link.href}">${link.label}</a>` : ''}
          ${active ? html`<button type="button" class="btn btn-sm btn-ghost btn-danger" data-cancel="${job.id}">${icon('stop', { size: 14 })}<span>İptal</span></button>` : ''}
        </div>
      </div>
      ${logsOpen ? html`<ol class="log-box">${logLines(job.logs || [])}</ol>` : ''}
    `.s;
    if (logsOpen) {
      const box = $('.log-box', node);
      if (box) box.scrollTop = box.scrollHeight;
    }
  };

  node.addEventListener('click', async (e) => {
    if (e.target.closest('[data-toggle-logs]')) {
      logsOpen = !logsOpen;
      render();
      return;
    }
    if (e.target.closest('[data-dismiss]')) {
      stopWatch();
      node.remove();
      if (opts.onDismiss) opts.onDismiss(job);
      return;
    }
    const ans = e.target.closest('[data-answer]');
    if (ans) {
      $$('[data-answer]', node).forEach((b) => (b.disabled = true));
      try {
        await respondJob(job.id, ans.dataset.answer === 'yes');
      } catch (err) {
        showError(err);
        $$('[data-answer]', node).forEach((b) => (b.disabled = false));
      }
      return;
    }
    handleJobClicks(e);
  });

  render();
  let watcher = null;
  const stopWatch = () => watcher && watcher.stop();
  if (isActive(initial) || typeof jobOrId === 'string') {
    watcher = watchJob(id, (j, err) => {
      if (!j) {
        job = { ...job, status: 'error', error: err ? err.message : 'İş bulunamadı.' };
        render();
        return;
      }
      if (j.status !== 'queued' || job.status !== 'queued') queuedSince = Date.now();
      job = j;
      render();
      if (opts.onUpdate) opts.onUpdate(job);
      if (!isActive(job) && !doneCalled) {
        doneCalled = true;
        if (opts.onDone) opts.onDone(job);
      }
    });
  } else if (!doneCalled && opts.onDone) {
    doneCalled = true;
    queueMicrotask(() => opts.onDone(job));
  }
  // "sırada" uyarısının zamanında görünmesi için
  const stuckTimer = setInterval(() => {
    if (!node.isConnected) return clearInterval(stuckTimer);
    if (job.status === 'queued') render();
    else clearInterval(stuckTimer);
  }, 5000);
  return {
    el: node,
    get job() {
      return job;
    },
    stop() {
      stopWatch();
      clearInterval(stuckTimer);
    },
  };
}

// ------------------------------------------------------------------ iş çekmecesi

let drawer = null;

export function openJobsDrawer(focusId = null) {
  if (drawer) {
    if (focusId) drawer.focus(focusId);
    return drawer.sheet;
  }
  const expanded = new Set(focusId ? [focusId] : []);
  const fullLogs = new Map();
  let jobs = [];
  let timer = null;
  const sheet = openSheet({
    title: 'İşler',
    subtitle: 'Arka planda çalışan ve son biten işler',
    icon: 'activity',
    className: 'drawer',
    size: 'drawer',
    body: html`<div class="drawer-list" aria-live="polite"><div class="view-loading"><span class="spinner"></span></div></div>`,
    onClose() {
      clearTimeout(timer);
      drawer = null;
    },
  });
  const list = $('.drawer-list', sheet.body);

  const loadLogs = async (id) => {
    try {
      const j = await api(`/api/jobs/${enc(id)}?since=0`);
      fullLogs.set(id, j.logs || []);
      const idx = jobs.findIndex((x) => x.id === id);
      if (idx >= 0) jobs[idx] = { ...jobs[idx], ...j };
    } catch {
      /* yok say */
    }
  };

  const row = (j) => {
    const k = kindInfo(j.kind);
    const open = expanded.has(j.id);
    const logs = fullLogs.get(j.id) || j.logs || [];
    const last = (j.logs || []).slice(-1)[0];
    const link = jobLink(j);
    return html`
      <li class="drow ${open ? 'is-open' : ''}" data-id="${j.id}">
        <button type="button" class="drow-head" data-expand="${j.id}" aria-expanded="${open}">
          <span class="job-icon">${icon(k.icon, { size: 18 })}</span>
          <span class="drow-titles">
            <strong>${j.title || k.label}</strong>
            <span class="drow-meta">${j.platform ? `${platformName(j.platform)} · ` : ''}${k.label} · ${fmtRel(j.created_at)}</span>
            ${!open && (isActive(j) ? last : j.status === 'error') ? html`<span class="drow-last">${j.status === 'error' ? friendlyError(j.error) : last.msg}</span>` : ''}
          </span>
          ${statusChip(j)}
          ${icon(open ? 'chevronUp' : 'chevronDown', { size: 18, cls: 'drow-chev' })}
        </button>
        ${open ? html`
          <div class="drow-body">
            ${j.status === 'waiting' && j.prompt ? html`<div class="job-prompt">${icon('hand', { size: 18 })}<div><strong>${j.prompt.type === 'confirm' ? 'Onayınız bekleniyor' : 'Tarayıcıda işlem gerekiyor'}</strong><p>${j.prompt.message}</p></div></div>` : ''}
            ${!isActive(j) ? html`<p class="job-result">${icon(j.status === 'done' ? 'checkCircle' : j.status === 'error' ? 'xCircle' : 'info', { size: 18 })}<span>${jobSummary(j)}</span></p>` : ''}
            ${logs.length ? html`<ol class="log-box">${logLines(logs)}</ol>` : html`<p class="muted small">Henüz günlük kaydı yok.</p>`}
            <div class="drow-actions">
              ${j.status === 'waiting' && j.prompt && j.prompt.type === 'confirm' ? html`<button type="button" class="btn btn-sm btn-primary" data-reopen="${j.id}">Yanıtla</button>` : ''}
              ${isActive(j) ? html`<button type="button" class="btn btn-sm btn-danger" data-cancel="${j.id}">${icon('stop', { size: 14 })}<span>İptal et</span></button>` : ''}
              ${link ? html`<a class="btn btn-sm" href="${link.href}" data-close>${link.label}</a>` : ''}
            </div>
          </div>` : ''}
      </li>`;
  };

  const render = () => {
    const act = jobs.filter(isActive);
    const done = jobs.filter((j) => !isActive(j));
    const scrollTop = sheet.body.scrollTop;
    list.innerHTML = html`
      ${!jobs.length ? html`
        <div class="empty compact">
          <div class="empty-art" aria-hidden="true">${icon('activity', { size: 28 })}</div>
          <h3 class="empty-title">Henüz iş yok</h3>
          <p class="empty-text">İlan oluşturma, yayınlama, tarama ve fiyat araştırması işleri burada görünür.</p>
        </div>` : ''}
      ${act.length ? html`<h3 class="drawer-h">Devam eden (${act.length})</h3><ul class="drows">${act.map(row)}</ul>` : ''}
      ${done.length ? html`<h3 class="drawer-h">Son işler</h3><ul class="drows">${done.map(row)}</ul>` : ''}
    `.s;
    for (const box of list.querySelectorAll('.log-box')) box.scrollTop = box.scrollHeight;
    sheet.body.scrollTop = scrollTop;
  };

  const load = async () => {
    clearTimeout(timer);
    try {
      jobs = await api('/api/jobs?limit=40');
      await Promise.all([...expanded].filter((id) => jobs.some((j) => j.id === id && (isActive(j) || !fullLogs.has(id)))).map(loadLogs));
      render();
    } catch (e) {
      if (!jobs.length) list.innerHTML = html`<p class="muted">${e.message}</p>`.s;
    }
    if (drawer) timer = setTimeout(load, document.hidden ? 8000 : 2000);
  };

  sheet.body.addEventListener('click', async (e) => {
    const exp = e.target.closest('[data-expand]');
    if (exp) {
      const id = exp.dataset.expand;
      if (expanded.has(id)) expanded.delete(id);
      else {
        expanded.add(id);
        await loadLogs(id);
      }
      render();
      return;
    }
    if (handleJobClicks(e)) setTimeout(load, 500);
  });

  drawer = {
    sheet,
    focus(id) {
      expanded.add(id);
      loadLogs(id).then(render);
    },
  };
  load();
  return sheet;
}

export function refreshRelTimes(root) {
  refreshTimes(root);
}
