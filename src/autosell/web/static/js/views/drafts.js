// İlanlarım: taslak ve yayındaki ilanların listesi.
import { api, enc } from '../api.js';
import { html, $, $$, fmtPrice, fmtNum, timeAgo, debounce, store } from '../util.js';
import { icon } from '../icons.js';
import { emptyState, errorState, pubChip, skeletonCards, spinner } from '../ui.js';
import { onJobsChange } from '../jobs.js';
import { replaceQuery } from '../router.js';

const FILTERS = [
  { key: 'all', label: 'Tümü' },
  { key: 'taslak', label: 'Taslak' },
  { key: 'yayinda', label: 'Yayında' },
  { key: 'sorun', label: 'Sorunlu' },
];

function statusesOf(d) {
  return d.platforms.map((p) => (d.publications[p] ? d.publications[p].status : 'none'));
}

function matchesFilter(d, f) {
  const st = statusesOf(d);
  if (f === 'yayinda') return st.includes('yayinda');
  if (f === 'sorun') return st.some((s) => s === 'hata' || s === 'iptal' || s === 'onay_bekliyor');
  if (f === 'taslak') return !st.includes('yayinda');
  return true;
}

export async function mount(root, ctx) {
  let drafts = null;
  let filter = ctx.query.get('f') || store.get('drafts.filter', 'all');
  if (!FILTERS.some((f) => f.key === filter)) filter = 'all';
  let q = '';
  let generating = new Set();

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">İlanlarım</h1>
        <p class="page-sub" data-sub>Taslaklarınız ve yayındaki ilanlarınız</p>
      </div>
      <div class="page-actions">
        <a class="btn btn-primary" href="#/yeni">${icon('plus', { size: 18, strokeWidth: 2.2 })}<span>Yeni ilan</span></a>
      </div>
    </header>
    <div class="toolbar">
      <div class="input-wrap has-prefix toolbar-search">
        <span class="input-prefix">${icon('search', { size: 18 })}</span>
        <label class="sr-only" for="drafts-q">İlanlarda ara</label>
        <input id="drafts-q" class="input" type="search" placeholder="İlanlarda ara…" autocomplete="off" data-q />
      </div>
      <div class="segmented" role="tablist" aria-label="Duruma göre süz" data-filters></div>
    </div>
    <div class="draft-grid" data-list aria-live="polite">${skeletonCards(6, 'skel-draft')}</div>`.s;

  const $list = $('[data-list]', root);
  const $filters = $('[data-filters]', root);
  const $sub = $('[data-sub]', root);

  function renderFilters() {
    const counts = Object.fromEntries(FILTERS.map((f) => [f.key, drafts ? drafts.filter((d) => matchesFilter(d, f.key)).length : 0]));
    $filters.innerHTML = html`${FILTERS.map((f) => html`
      <button type="button" class="seg" role="tab" aria-selected="${filter === f.key}" data-filter="${f.key}">
        ${f.label}${drafts ? html` <span class="count">${counts[f.key]}</span>` : ''}
      </button>`)}`.s;
  }

  function card(d) {
    const gen = generating.has(d.id);
    return html`
      <a class="draft-card card" href="#/ilan/${enc(d.id)}">
        <div class="draft-cover">
          ${d.cover ? html`<img src="${d.cover}" alt="" loading="lazy" data-fallback />` : html`<span class="img-fallback">${icon('image', { size: 26 })}</span>`}
          ${d.photo_count > 1 ? html`<span class="cover-count">${icon('image', { size: 13 })}${d.photo_count}</span>` : ''}
          ${gen ? html`<span class="cover-flag">${spinner(12)}Oluşturuluyor…</span>` : !d.generated ? html`<span class="cover-flag is-muted">${icon('sparkles', { size: 13 })}Yapay zekâ bekliyor</span>` : ''}
        </div>
        <div class="draft-body">
          <h2 class="draft-title">${d.title || 'Adsız ilan'}</h2>
          <div class="draft-price ${d.price == null ? 'is-empty' : ''}">${d.price == null ? 'Fiyat girilmedi' : fmtPrice(d.price, d.currency)}</div>
          <div class="chips draft-pubs">${d.platforms.map((p) => pubChip(p, d.publications[p]))}</div>
          <div class="draft-meta">${icon('clock', { size: 13 })}${timeAgo(d.updated_at, 'Güncellendi ')}</div>
        </div>
      </a>`;
  }

  function render() {
    renderFilters();
    if (!drafts) return;
    $sub.textContent = drafts.length ? `${fmtNum(drafts.length)} ilan` : 'Taslaklarınız ve yayındaki ilanlarınız';
    if (!drafts.length) {
      $list.className = 'draft-grid is-empty';
      $list.innerHTML = html`<div class="card">${emptyState({
        icon: 'tag',
        title: 'Henüz ilanınız yok',
        text: 'Ürünün birkaç fotoğrafını çekin, kısa bir not yazın; başlığı, açıklamayı ve kategoriyi yapay zekâ hazırlasın.',
        action: html`<a class="btn btn-primary btn-lg" href="#/yeni">${icon('sparkles', { size: 18 })}<span>İlk ilanını oluştur</span></a>`,
      })}</div>`.s;
      return;
    }
    const needle = q.trim().toLocaleLowerCase('tr');
    const shown = drafts.filter((d) => matchesFilter(d, filter) && (!needle || (d.title || '').toLocaleLowerCase('tr').includes(needle)));
    if (!shown.length) {
      $list.className = 'draft-grid is-empty';
      $list.innerHTML = html`<div class="card">${emptyState({
        icon: 'search',
        title: 'Eşleşen ilan yok',
        text: needle ? `“${q.trim()}” için sonuç bulunamadı.` : 'Bu filtrede ilan bulunmuyor.',
        action: html`<button type="button" class="btn" data-clear>Filtreyi temizle</button>`,
      })}</div>`.s;
      return;
    }
    $list.className = 'draft-grid';
    $list.innerHTML = html`${shown.map(card)}`.s;
  }

  async function load() {
    try {
      const data = await api('/api/drafts', { signal: ctx.signal });
      if (!ctx.alive()) return;
      drafts = data;
      render();
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      if (!drafts) {
        $list.className = 'draft-grid is-empty';
        $list.innerHTML = html`<div class="card">${errorState(e)}</div>`.s;
      }
    }
  }

  $filters.addEventListener('click', (e) => {
    const b = e.target.closest('[data-filter]');
    if (!b) return;
    filter = b.dataset.filter;
    store.set('drafts.filter', filter);
    replaceQuery({ f: filter === 'all' ? '' : filter });
    render();
  });
  $('[data-q]', root).addEventListener('input', debounce((e) => {
    q = e.target.value;
    render();
  }, 120));
  root.addEventListener('click', (e) => {
    if (e.target.closest('[data-clear]')) {
      q = '';
      filter = 'all';
      $('[data-q]', root).value = '';
      replaceQuery({});
      render();
    }
    if (e.target.closest('[data-action="retry"]')) load();
  });

  ctx.scope.cleanup(onJobsChange((jobs) => {
    const next = new Set(jobs.filter((j) => j.kind === 'generate' || j.kind === 'publish').map((j) => j.draft_id).filter(Boolean));
    const changed = next.size !== generating.size || [...next].some((id) => !generating.has(id));
    generating = new Set(jobs.filter((j) => j.kind === 'generate').map((j) => j.draft_id));
    if (changed && drafts) load();
  }));
  ctx.scope.on(document, 'autosell:job-finished', (e) => {
    if (e.detail && e.detail.draft_id) load();
  });
  ctx.scope.interval(load, 15000);
  await load();
  return {};
}
