// Fırsatlar: takip listelerinden bulunan al-sat fırsatları, süzgeçler ve hızlı işlemler.
import { api } from '../api.js';
import { html, el, $, $$, fmtPrice, fmtSignedPrice, fmtPct, fmtNum, timeAgo, safeUrl, store, platformName } from '../util.js';
import { icon } from '../icons.js';
import { toast, showError, emptyState, errorState, scoreRing, riskChip, skeletonCards } from '../ui.js';
import { replaceQuery } from '../router.js';

export const DEAL_STATUSES = [
  { key: 'yeni', label: 'Yeni' },
  { key: 'favori', label: 'Favori' },
  { key: 'incelendi', label: 'İncelendi' },
  { key: '', label: 'Tümü' },
  { key: 'gizli', label: 'Gizlenen' },
];

const DEFAULTS = { status: 'yeni', minScore: 0, watch: '', all: false };

/** Tek fırsat kartı (liste ve panelde kullanılır). */
export function dealCard({ deal, listing }) {
  const img = safeUrl(listing.image_url);
  const url = safeUrl(listing.url);
  const ai = deal.ai || null;
  const dropped = listing.prev_price && listing.price && listing.price < listing.prev_price;
  const risks = deal.risk_flags || [];
  const order = { yuksek: 0, orta: 1, dusuk: 2 };
  const sortedRisks = [...risks].sort((a, b) => order[a.level] - order[b.level]);
  return html`
    <article class="deal-card card ${deal.is_deal ? '' : 'is-candidate'}" data-deal="${deal.id}" data-status="${deal.status}">
      <div class="deal-body">
        <div class="deal-thumb">
          ${img ? html`<img src="${img}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback="remove" />` : ''}
          ${icon('image', { size: 22 })}
          <span class="deal-plat" title="${platformName(listing.platform)}"><i class="pdot pdot-${listing.platform}"></i></span>
        </div>
        <div class="deal-main">
          <div class="deal-top">
            <h3 class="deal-title"><a href="#/firsat/${deal.id}" class="stretched">${listing.title}</a></h3>
            ${scoreRing(deal.score, { size: 46, label: 'Fırsat puanı' })}
          </div>
          <div class="deal-prices">
            <strong class="deal-price">${fmtPrice(listing.price, listing.currency)}</strong>
            ${dropped ? html`<s class="deal-prev" title="Önceki fiyat">${fmtPrice(listing.prev_price, listing.currency)}</s>` : ''}
            <span class="deal-market">Piyasa ${fmtPrice(deal.est_value)}</span>
          </div>
          <div class="deal-profit">
            <span class="profit-pill ${deal.est_profit > 0 ? 'is-pos' : 'is-neg'}">${icon(deal.est_profit > 0 ? 'trendUp' : 'trendDown', { size: 15 })}${fmtSignedPrice(deal.est_profit)}<span class="profit-label">tahmini kâr</span></span>
            <span class="margin">${fmtPct(deal.margin_pct)} marj</span>
            ${!deal.is_deal ? html`<span class="chip chip-xs">Aday</span>` : ''}
            ${deal.fast && !deal.fast.elendi && deal.fast.ilan_turu ? html`<span class="chip chip-xs chip-fast" title="Hızlı karar motoru (${deal.fast.motor || ''}): aynı ürün, kusur ya da şüphe işareti yok">${icon('zap', { size: 11 })}Kontrol temiz</span>` : ''}
            ${deal.status === 'favori' ? html`<span class="chip chip-xs chip-warning">${icon('starFill', { size: 11 })}Favori</span>` : deal.status === 'incelendi' ? html`<span class="chip chip-xs">${icon('check', { size: 11 })}İncelendi</span>` : ''}
          </div>
          ${sortedRisks.length ? html`<div class="chips deal-risks">${sortedRisks.slice(0, 3).map(riskChip)}${sortedRisks.length > 3 ? html`<span class="chip chip-xs">+${sortedRisks.length - 3}</span>` : ''}</div>` : ''}
          ${ai && ai.yorum ? html`
            <div class="deal-ai">
              ${icon('bot', { size: 16 })}
              <p><span class="deal-ai-text">${ai.yorum}</span>${ai.pazarlik_teklifi ? html` <strong class="deal-offer">Teklif: ${fmtPrice(ai.pazarlik_teklifi)}</strong>` : ''}</p>
            </div>` : ''}
          <div class="deal-meta">
            ${listing.location ? html`<span>${icon('pin', { size: 14 })}${listing.location}</span>` : ''}
            <span>${icon('clock', { size: 14 })}${timeAgo(listing.first_seen)}</span>
            <span>${fmtNum(deal.comps_count)} emsal</span>
          </div>
        </div>
      </div>
      <div class="deal-actions">
        ${url ? html`<a class="btn btn-sm" href="${url}" target="_blank" rel="noopener">${icon('external', { size: 15 })}<span>İlana git</span></a>` : ''}
        <button type="button" class="btn btn-sm btn-ghost ${deal.status === 'favori' ? 'is-on' : ''}" data-set="favori" aria-pressed="${deal.status === 'favori'}" title="Favorilere ekle">${icon(deal.status === 'favori' ? 'starFill' : 'star', { size: 16 })}<span>Favori</span></button>
        <button type="button" class="btn btn-sm btn-ghost ${deal.status === 'incelendi' ? 'is-on' : ''}" data-set="incelendi" aria-pressed="${deal.status === 'incelendi'}" title="İncelendi olarak işaretle">${icon('check', { size: 16 })}<span>İncelendi</span></button>
        ${deal.status === 'gizli'
          ? html`<button type="button" class="btn btn-sm btn-ghost" data-set="yeni" title="Geri getir">${icon('eye', { size: 16 })}<span>Geri getir</span></button>`
          : html`<button type="button" class="btn btn-sm btn-ghost" data-set="gizli" title="Gizle">${icon('eyeOff', { size: 16 })}<span>Gizle</span></button>`}
      </div>
    </article>`;
}

/** Durum değiştirir; geri alma için önceki durumu döndürür. */
export async function setDealStatus(id, status) {
  return api.put(`/api/deals/${id}`, { status });
}

export async function mount(root, ctx) {
  const saved = { ...DEFAULTS, ...store.get('deals.filters', {}) };
  const f = { ...saved };
  if (ctx.query.has('watch')) f.watch = ctx.query.get('watch');
  if (ctx.query.has('durum')) f.status = ctx.query.get('durum');
  let watches = [];
  let items = null;
  let loading = false;
  let filtersOpen = false;

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">Fırsatlar</h1>
        <p class="page-sub" data-sub>Takip listelerinizde piyasanın altında bulunan ilanlar</p>
      </div>
      <div class="page-actions">
        <a class="btn" href="#/takip">${icon('eye', { size: 18 })}<span>Takip listeleri</span></a>
        <a class="btn" href="#/arastir">${icon('chart', { size: 18 })}<span>Fiyat araştır</span></a>
      </div>
    </header>
    <section class="filters card" aria-label="Süzgeçler">
      <div class="filters-top">
        <div class="segmented" role="tablist" aria-label="Duruma göre" data-status></div>
        <button type="button" class="btn btn-sm filters-toggle" data-toggle-filters aria-expanded="false" aria-controls="deal-filters">${icon('filter', { size: 16 })}<span>Süzgeçler</span><span class="badge" data-fcount hidden></span></button>
      </div>
      <div class="filters-row" id="deal-filters" data-filter-row>
        <div class="field">
          <label class="label" for="f-watch">Takip listesi</label>
          <select id="f-watch" class="select" data-watch><option value="">Tüm listeler</option></select>
        </div>
        <div class="field range-field">
          <label class="label" for="f-score">En düşük puan <output class="range-out" data-score-out for="f-score">${f.minScore}</output></label>
          <input id="f-score" type="range" min="0" max="90" step="5" value="${f.minScore}" data-score />
        </div>
        <label class="switch filters-switch">
          <input type="checkbox" data-all ${f.all ? 'checked' : ''} />
          <span class="switch-track" aria-hidden="true"></span>
          <span class="switch-text"><span class="switch-label">Tüm adaylar</span><span class="switch-hint">Kâr eşiğini geçmeyenleri de göster</span></span>
        </label>
        <button type="button" class="btn btn-ghost btn-sm" data-reset>Sıfırla</button>
      </div>
    </section>
    <div class="deal-grid" data-list aria-live="polite">${skeletonCards(4, 'skel-deal')}</div>`.s;

  const $list = $('[data-list]', root);
  const $status = $('[data-status]', root);
  const $watch = $('[data-watch]', root);
  const $score = $('[data-score]', root);
  const $scoreOut = $('[data-score-out]', root);
  const $all = $('[data-all]', root);
  const $sub = $('[data-sub]', root);

  function persist() {
    store.set('deals.filters', { status: f.status, minScore: f.minScore, watch: f.watch, all: f.all });
    replaceQuery({ watch: f.watch, durum: f.status === DEFAULTS.status ? '' : f.status });
  }

  function activeFilterCount() {
    return (f.watch ? 1 : 0) + (f.minScore > 0 ? 1 : 0) + (f.all ? 1 : 0);
  }

  function renderControls() {
    $status.innerHTML = html`${DEAL_STATUSES.map((s) => html`<button type="button" role="tab" class="seg" aria-selected="${f.status === s.key}" data-st="${s.key}">${s.label}</button>`)}`.s;
    $watch.innerHTML = html`<option value="">Tüm listeler</option>${watches.map((w) => html`<option value="${w.id}" ${String(w.id) === String(f.watch) ? 'selected' : ''}>${w.name} (${platformName(w.platform)})</option>`)}`.s;
    $score.value = f.minScore;
    $scoreOut.textContent = f.minScore ? `${f.minScore}+` : 'Tümü';
    $all.checked = f.all;
    const n = activeFilterCount();
    const badge = $('[data-fcount]', root);
    badge.textContent = String(n);
    badge.hidden = !n;
    root.querySelector('.filters').classList.toggle('is-open', filtersOpen);
    $('[data-toggle-filters]', root).setAttribute('aria-expanded', String(filtersOpen));
  }

  function render() {
    if (!items) return;
    $sub.textContent = items.length
      ? `${fmtNum(items.length)} ${f.all ? 'ilan' : 'fırsat'} · puana göre sıralı`
      : 'Takip listelerinizde piyasanın altında bulunan ilanlar';
    if (!items.length) {
      const filtered = f.status !== '' || activeFilterCount();
      $list.className = 'deal-grid is-empty';
      $list.innerHTML = html`<div class="card">${emptyState(watches.length || filtered ? {
        icon: 'target',
        title: filtered ? 'Bu süzgeçlerde fırsat yok' : 'Henüz fırsat bulunmadı',
        text: filtered ? 'Süzgeçleri gevşetin ya da “Tüm adaylar”ı açın. Takip listeleriniz tarandıkça yeni fırsatlar burada görünür.' : 'Takip listeleriniz tarandıkça piyasanın altındaki ilanlar burada görünür.',
        action: filtered ? html`<button type="button" class="btn" data-reset>Süzgeçleri sıfırla</button>` : html`<a class="btn btn-primary" href="#/takip">Takip listelerine git</a>`,
      } : {
        icon: 'eye',
        title: 'Önce bir takip listesi ekleyin',
        text: 'Aradığınız ürünü (ör. “iPhone 13 128 GB”) takip listesine ekleyin; AutoSell düzenli tarayıp kârlı ilanları puanlar.',
        action: html`<a class="btn btn-primary" href="#/takip?yeni=1">${icon('plus', { size: 18 })}<span>Takip ekle</span></a>`,
      })}</div>`.s;
      return;
    }
    $list.className = 'deal-grid';
    $list.innerHTML = html`${items.map(dealCard)}`.s;
  }

  async function load() {
    if (loading) return;
    loading = true;
    $list.classList.add('is-refreshing');
    const qs = new URLSearchParams({ limit: '200' });
    if (f.status) qs.set('status', f.status);
    if (f.minScore) qs.set('min_score', String(f.minScore));
    if (f.watch) qs.set('watch_id', String(f.watch));
    if (f.all) qs.set('all', '1');
    try {
      const data = await api(`/api/deals?${qs}`, { signal: ctx.signal });
      if (!ctx.alive()) return;
      items = data;
      render();
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      if (!items) {
        $list.className = 'deal-grid is-empty';
        $list.innerHTML = html`<div class="card">${errorState(e)}</div>`.s;
      } else showError(e);
    } finally {
      loading = false;
      $list.classList.remove('is-refreshing');
    }
  }

  api('/api/watches', { signal: ctx.signal }).then((w) => {
    if (!ctx.alive()) return;
    watches = w;
    renderControls();
    if (items) render();
  }).catch(() => {});

  root.addEventListener('click', async (e) => {
    const st = e.target.closest('[data-st]');
    if (st) {
      f.status = st.dataset.st;
      persist();
      renderControls();
      load();
      return;
    }
    if (e.target.closest('[data-toggle-filters]')) {
      filtersOpen = !filtersOpen;
      renderControls();
      return;
    }
    if (e.target.closest('[data-reset]')) {
      Object.assign(f, DEFAULTS);
      persist();
      renderControls();
      load();
      return;
    }
    if (e.target.closest('[data-action="retry"]')) {
      load();
      return;
    }
    const setBtn = e.target.closest('[data-set]');
    if (setBtn) {
      const card = setBtn.closest('[data-deal]');
      const id = Number(card.dataset.deal);
      const item = items.find((x) => x.deal.id === id);
      if (!item) return;
      const prev = item.deal.status;
      let next = setBtn.dataset.set;
      if (next === prev && next !== 'yeni') next = 'yeni';
      setBtn.disabled = true;
      try {
        await setDealStatus(id, next);
        item.deal.status = next;
        const keep = f.status === '' ? next !== 'gizli' : f.status === next;
        if (!keep) {
          card.classList.add('is-leaving');
          setTimeout(() => {
            items = items.filter((x) => x.deal.id !== id);
            render();
          }, 220);
        } else {
          card.replaceWith(el(dealCard(item)));
        }
        const msgs = { favori: 'Favorilere eklendi.', incelendi: 'İncelendi olarak işaretlendi.', gizli: 'Fırsat gizlendi.', yeni: prev === 'gizli' ? 'Fırsat geri getirildi.' : 'İşaret kaldırıldı.' };
        toast.success(msgs[next] || 'Güncellendi.', next === 'gizli' ? {
          action: {
            label: 'Geri al',
            onClick: async () => {
              try {
                await setDealStatus(id, prev);
                load();
              } catch (err) {
                showError(err);
              }
            },
          },
        } : {});
      } catch (err) {
        showError(err);
        setBtn.disabled = false;
      }
    }
  });

  $watch.addEventListener('change', () => {
    f.watch = $watch.value;
    persist();
    renderControls();
    load();
  });
  $score.addEventListener('input', () => {
    f.minScore = Number($score.value);
    $scoreOut.textContent = f.minScore ? `${f.minScore}+` : 'Tümü';
  });
  $score.addEventListener('change', () => {
    persist();
    renderControls();
    load();
  });
  $all.addEventListener('change', () => {
    f.all = $all.checked;
    persist();
    renderControls();
    load();
  });

  renderControls();
  await load();
  ctx.scope.interval(load, 30000);
  ctx.scope.on(document, 'autosell:job-finished', (e) => {
    if (e.detail && e.detail.kind === 'scan') load();
  });
  return {};
}
