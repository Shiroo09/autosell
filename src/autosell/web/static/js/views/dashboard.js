// Panel: özet istatistikler, uyarılar, aktif işler, günün fırsatları ve hızlı işlemler.
import { api, enc } from '../api.js';
import { html, $, fmtNum, fmtPrice, fmtSignedPrice, fmtPct, timeAgo, safeUrl, platformName } from '../util.js';
import { icon } from '../icons.js';
import { callout, emptyState, errorState, scoreRing, pubChip, skeletonLines } from '../ui.js';
import { onJobsChange, statusChip, kindInfo, openJobsDrawer, remoteButton } from '../jobs.js';
import { setStatus } from '../state.js';

function greeting() {
  const h = new Date().getHours();
  if (h < 6) return 'İyi geceler';
  if (h < 12) return 'Günaydın';
  if (h < 18) return 'İyi günler';
  return 'İyi akşamlar';
}

const today = () => new Intl.DateTimeFormat('tr-TR', { weekday: 'long', day: 'numeric', month: 'long' }).format(new Date());

function statTile({ href, label, value, icon: ic, tone = '', sub = '' }) {
  return html`
    <a class="stat card" href="${href}">
      <span class="stat-top"><span class="icon-tile ${tone}">${icon(ic, { size: 18 })}</span><span class="stat-label">${label}</span></span>
      <strong class="stat-value">${value}</strong>
      ${sub ? html`<span class="stat-sub">${sub}</span>` : ''}
    </a>`;
}

export function dealRow({ deal, listing }) {
  const img = safeUrl(listing.image_url);
  return html`
    <li>
      <a class="deal-row" href="#/firsat/${deal.id}">
        <span class="deal-row-thumb">${img ? html`<img src="${img}" alt="" loading="lazy" referrerpolicy="no-referrer" data-fallback="remove" />` : ''}${icon('image', { size: 18 })}</span>
        <span class="deal-row-main">
          <span class="deal-row-title">${listing.title}</span>
          <span class="deal-row-meta"><i class="pdot pdot-${listing.platform}" aria-hidden="true"></i>${fmtPrice(listing.price, listing.currency)} <span class="muted">· piyasa ${fmtPrice(deal.est_value)}</span></span>
        </span>
        <span class="deal-row-profit ${deal.est_profit > 0 ? 'is-pos' : ''}">${fmtSignedPrice(deal.est_profit)}<small>${fmtPct(deal.margin_pct)}</small></span>
        ${scoreRing(deal.score, { size: 40, label: 'Fırsat puanı' })}
      </a>
    </li>`;
}

function jobRow(j) {
  const k = kindInfo(j.kind);
  const last = (j.logs || []).slice(-1)[0];
  return html`
    <li class="mini-job">
      <button type="button" class="mini-job-btn" data-open-job="${j.id}">
        <span class="job-icon">${icon(k.icon, { size: 18 })}</span>
        <span class="mini-job-main">
          <strong>${j.title}</strong>
          <span class="muted small">${j.status === 'waiting' && j.prompt ? j.prompt.message : last ? last.msg : k.label}</span>
        </span>
        ${statusChip(j)}
      </button>
      ${j.status === 'waiting' ? html`<div class="mini-job-actions">${remoteButton(j)}</div>` : ''}
      ${j.status !== 'waiting' ? html`<div class="progress"><span></span></div>` : ''}
    </li>`;
}

export async function mount(root, ctx) {
  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">${greeting()}!</h1>
        <p class="page-sub">${today()} · İlanlarınız ve fırsatlarınızın özeti</p>
      </div>
      <div class="page-actions desktop-only">
        <a class="btn" href="#/arastir">${icon('chart', { size: 18 })}<span>Fiyat araştır</span></a>
        <a class="btn btn-primary" href="#/yeni">${icon('plus', { size: 18, strokeWidth: 2.2 })}<span>Yeni ilan</span></a>
      </div>
    </header>
    <div class="dash-alerts" data-alerts></div>
    <section class="stats" data-stats aria-label="Özet">
      ${[1, 2, 3, 4].map(() => html`<div class="stat card"><div class="skel skel-line" style="width:60%"></div><div class="skel" style="height:30px;width:40%;margin-top:10px"></div></div>`)}
    </section>
    <div class="dash-grid">
      <div class="dash-main">
        <section class="card" aria-labelledby="dash-deals-t">
          <header class="card-head">
            <h2 class="card-title" id="dash-deals-t">${icon('target', { size: 18 })}Günün fırsatları</h2>
            <a class="head-actions small" href="#/firsatlar">Tümünü gör ${icon('chevronRight', { size: 16 })}</a>
          </header>
          <div data-deals class="card-body">${skeletonLines(4)}</div>
        </section>
        <section class="card" aria-labelledby="dash-drafts-t">
          <header class="card-head">
            <h2 class="card-title" id="dash-drafts-t">${icon('tag', { size: 18 })}Son ilanlarım</h2>
            <a class="head-actions small" href="#/ilanlar">Tümü ${icon('chevronRight', { size: 16 })}</a>
          </header>
          <div data-drafts class="card-body">${skeletonLines(3)}</div>
        </section>
      </div>
      <aside class="dash-side">
        <section class="card card-pad quick" aria-labelledby="dash-quick-t">
          <h2 class="card-title" id="dash-quick-t">Hızlı işlemler</h2>
          <div class="quick-grid">
            <a class="quick-btn is-primary" href="#/yeni">${icon('sparkles', { size: 22 })}<span>Yeni ilan</span></a>
            <a class="quick-btn" href="#/arastir">${icon('chart', { size: 22 })}<span>Fiyat araştır</span></a>
            <a class="quick-btn" href="#/takip?yeni=1">${icon('plus', { size: 22 })}<span>Takip ekle</span></a>
            <a class="quick-btn" href="#/takip">${icon('eye', { size: 22 })}<span>Takip listeleri</span></a>
          </div>
        </section>
        <section class="card" aria-labelledby="dash-jobs-t" data-jobs-card hidden>
          <header class="card-head">
            <h2 class="card-title" id="dash-jobs-t">${icon('activity', { size: 18 })}Süren işler</h2>
            <button type="button" class="btn btn-ghost btn-sm head-actions" data-all-jobs>Tümü</button>
          </header>
          <ul class="mini-jobs" data-jobs></ul>
        </section>
        <section class="card card-pad" data-ai aria-label="Yapay zekâ durumu">${skeletonLines(2)}</section>
      </aside>
    </div>`.s;

  const $alerts = $('[data-alerts]', root);
  const $stats = $('[data-stats]', root);
  const $deals = $('[data-deals]', root);
  const $drafts = $('[data-drafts]', root);
  const $ai = $('[data-ai]', root);
  const $jobsCard = $('[data-jobs-card]', root);
  const $jobs = $('[data-jobs]', root);

  root.addEventListener('click', (e) => {
    const j = e.target.closest('[data-open-job]');
    if (j) openJobsDrawer(j.dataset.openJob);
    if (e.target.closest('[data-all-jobs]')) openJobsDrawer();
    if (e.target.closest('[data-action="retry"]')) load();
  });

  ctx.scope.cleanup(onJobsChange((jobs) => {
    $jobsCard.hidden = !jobs.length;
    const key = jobs.map((j) => `${j.id}:${j.status}:${j.log_count}`).join('|');
    if ($jobs.dataset.key === key) return;
    $jobs.dataset.key = key;
    $jobs.innerHTML = html`${jobs.slice(0, 5).map(jobRow)}`.s;
  }));

  function renderStatus(s) {
    const st = s.stats || {};
    $stats.innerHTML = html`
      ${statTile({ href: '#/ilanlar', label: 'Taslak ilan', value: fmtNum(st.drafts), icon: 'tag' })}
      ${statTile({ href: '#/ilanlar?f=yayinda', label: 'Yayında', value: fmtNum(st.published), icon: 'checkCircle', tone: 'is-success' })}
      ${statTile({ href: '#/takip', label: 'Aktif takip', value: fmtNum(st.active_watches), icon: 'eye', tone: 'is-neutral', sub: st.watches ? `${fmtNum(st.watches)} listeden` : '' })}
      ${statTile({ href: '#/firsatlar', label: 'Bugünkü fırsat', value: fmtNum(st.deals_today), icon: 'target', tone: 'is-warning', sub: st.deals ? `toplam ${fmtNum(st.deals)}` : '' })}`.s;

    const alerts = [];
    if (!s.seller_ready) {
      alerts.push(callout({
        tone: 'warning',
        title: 'İl/ilçe girilmedi',
        text: 'İlan verirken konum zorunlu. Satıcı profilinizde il ve ilçeyi girin.',
        action: html`<a class="btn btn-sm" href="#/ayarlar?b=seller">Konumu gir</a>`,
      }));
    }
    const autoOn = Object.entries(s.platforms || {}).filter(([, p]) => p.auto_publish);
    if (autoOn.length) {
      alerts.push(callout({
        tone: 'info',
        icon: 'zap',
        title: 'Otomatik yayın açık',
        text: `${autoOn.map(([k]) => platformName(k)).join(', ')} için son "Yayınla" adımı onay beklemeden tıklanır.`,
        action: html`<a class="btn btn-sm" href="#/ayarlar?b=platforms">Ayarlar</a>`,
      }));
    }
    $alerts.innerHTML = html`${alerts}`.s;
    $alerts.hidden = !alerts.length;

    const ai = s.ai || {};
    $ai.innerHTML = ai.configured
      ? html`
        <div class="ai-card">
          <span class="icon-tile is-success">${icon('bot', { size: 20 })}</span>
          <div class="grow">
            <h2 class="card-title">Yapay zekâ hazır</h2>
            <p class="muted small ai-desc">${ai.description || ai.provider}</p>
          </div>
          <a class="btn btn-ghost btn-sm" href="#/ayarlar?b=ai">Ayarlar</a>
        </div>`.s
      : html`
        <div class="ai-card">
          <span class="icon-tile is-warning">${icon('bot', { size: 20 })}</span>
          <div class="grow">
            <h2 class="card-title">Yapay zekâ ayarlı değil</h2>
            <p class="muted small">${ai.description || 'İlan metinlerini oluşturmak için bir sağlayıcı tanımlayın.'}</p>
          </div>
        </div>
        <a class="btn btn-primary btn-block" href="#/ayarlar?b=ai" style="margin-top:12px">${icon('key', { size: 18 })}<span>Yapay zekâyı ayarla</span></a>`.s;
  }

  function renderDeals(deals) {
    if (!deals.length) {
      $deals.innerHTML = emptyState({
        icon: 'target',
        title: 'Henüz fırsat yok',
        text: 'Takip listesi ekleyin; AutoSell ilanları düzenli tarayıp piyasanın altındaki fırsatları burada gösterir.',
        action: html`<a class="btn btn-primary" href="#/takip?yeni=1">${icon('plus', { size: 18 })}<span>Takip ekle</span></a>`,
      }).s;
      $deals.classList.add('is-empty');
      return;
    }
    $deals.classList.remove('is-empty');
    $deals.innerHTML = html`<ul class="deal-rows">${deals.map(dealRow)}</ul>`.s;
  }

  function renderDrafts(drafts) {
    if (!drafts.length) {
      $drafts.innerHTML = emptyState({
        icon: 'tag',
        title: 'İlk ilanınızı oluşturun',
        text: 'Birkaç fotoğraf ve kısa bir not yeter; başlığı ve açıklamayı yapay zekâ yazar.',
        action: html`<a class="btn btn-primary" href="#/yeni">${icon('sparkles', { size: 18 })}<span>Yeni ilan</span></a>`,
      }).s;
      return;
    }
    $drafts.innerHTML = html`
      <ul class="draft-rows">
        ${drafts.slice(0, 4).map((d) => html`
          <li>
            <a class="draft-row" href="#/ilan/${enc(d.id)}">
              <span class="draft-row-thumb">${d.cover ? html`<img src="${d.cover}" alt="" loading="lazy" />` : icon('image', { size: 18 })}</span>
              <span class="draft-row-main">
                <span class="draft-row-title">${d.title}</span>
                <span class="draft-row-meta">${fmtPrice(d.price, d.currency)} · ${timeAgo(d.updated_at)}</span>
              </span>
              <span class="draft-row-pubs">${d.platforms.map((p) => pubChip(p, d.publications[p], { withName: false }))}</span>
            </a>
          </li>`)}
      </ul>`.s;
  }

  let first = true;
  async function load() {
    try {
      const [s, deals, drafts] = await Promise.all([
        api('/api/status', { signal: ctx.signal }),
        api('/api/deals?limit=5', { signal: ctx.signal }),
        api('/api/drafts', { signal: ctx.signal }),
      ]);
      if (!ctx.alive()) return;
      setStatus(s);
      renderStatus(s);
      renderDeals(deals);
      renderDrafts(drafts);
      first = false;
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      if (first) {
        $stats.innerHTML = '';
        $deals.innerHTML = errorState(e).s;
      }
    }
  }

  await load();
  ctx.scope.interval(load, 5000);
  ctx.scope.on(document, 'autosell:job-finished', () => load());
  return {};
}
