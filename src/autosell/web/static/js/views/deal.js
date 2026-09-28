// Fırsat ayrıntısı: gerekçeler, emsaller, fiyat geçmişi ve yapay zekâ değerlendirmesi.
import { api } from '../api.js';
import { html, $, fmtPrice, fmtSignedPrice, fmtPct, fmtNum, fmtDateTime, timeAgo, safeUrl, hostOf, platformName, isNum } from '../util.js';
import { icon } from '../icons.js';
import { toast, showError, emptyState, errorState, scoreRing, riskChip, platformBadge } from '../ui.js';
import { mountPriceHistory, simMeter } from '../charts.js';
import { setDealStatus } from './deals.js';

const RISK_LEVEL = { dusuk: { label: 'Düşük', tone: 'success' }, orta: { label: 'Orta', tone: 'orange' }, yuksek: { label: 'Yüksek', tone: 'danger' } };

function metric(label, value, { tone = '', sub = '' } = {}) {
  return html`<div class="metric ${tone}"><span class="metric-label">${label}</span><strong class="metric-value">${value}</strong>${sub ? html`<span class="metric-sub">${sub}</span>` : ''}</div>`;
}

const FAST_KIND = {
  urun: ['Ürünün kendisi', 'is-pos'],
  aksesuar_parca: ['Aksesuar / yedek parça', 'is-neg'],
  alim_takas: ['Alım ya da takas ilanı', 'is-neg'],
  diger: ['Başka bir şey', 'is-neg'],
};

function pctOf(v) {
  return isNum(v) ? `%${Math.round(v * 100)}` : '—';
}

/** Hızlı karar motoru (Jev / Laya) sonucu. */
function fastCard(fast) {
  if (!fast || !fast.ilan_turu) return '';
  const [kind, tone] = FAST_KIND[fast.ilan_turu] || [fast.ilan_turu, ''];
  const motor = { jev: 'Jev', laya: 'Laya' }[fast.motor] || fast.motor || '';
  return html`
    <section class="card" aria-labelledby="fast-t">
      <header class="card-head">
        <h2 class="card-title" id="fast-t">${icon('zap', { size: 18 })}Hızlı kontrol${motor ? html` <span class="muted">(${motor})</span>` : ''}</h2>
        <span class="head-actions">${fast.elendi ? html`<span class="chip chip-danger">${icon('x', { size: 13 })}Elendi</span>` : html`<span class="chip chip-success">${icon('check', { size: 13 })}Temiz</span>`}</span>
      </header>
      <div class="card-body fast-box">
        <div class="fast-grid">
          ${metric('Satılan', kind, { tone })}
          ${metric('Emsallerle aynı ürün', pctOf(fast.ayni_urun), { sub: 'olasılık', tone: isNum(fast.ayni_urun) && fast.ayni_urun < 0.4 ? 'is-neg' : '' })}
          ${metric('Arıza / hasar / kilit', pctOf(fast.kusurlu), { sub: 'olasılık', tone: isNum(fast.kusurlu) && fast.kusurlu >= 0.6 ? 'is-neg' : '' })}
          ${metric('Kapora / kayıt dışı', pctOf(fast.supheli), { sub: 'olasılık', tone: isNum(fast.supheli) && fast.supheli >= 0.6 ? 'is-neg' : '' })}
        </div>
        <p class="muted small">Karar motoru ilanı saniyeler içinde inceledi; metin yazmaz, yalnızca olasılık verir.</p>
      </div>
    </section>`;
}

export async function mount(root, ctx) {
  const id = Number(ctx.params[0]);
  let data = null;

  root.innerHTML = html`<div class="view-loading"><span class="spinner"></span><span class="sr-only">Fırsat yükleniyor…</span></div>`.s;

  function render() {
    const { deal, listing } = data;
    const url = safeUrl(listing.url);
    const img = safeUrl(listing.image_url);
    const ai = deal.ai || null;
    const dropped = listing.prev_price && listing.price && listing.price < listing.prev_price;
    const risks = deal.risk_flags || [];
    ctx.setTitle(listing.title);
    root.innerHTML = html`
      <header class="page-head">
        <div class="page-head-main">
          <a class="page-back desktop-only" href="#/firsatlar">${icon('chevronLeft', { size: 18 })}Fırsatlar</a>
          <h1 class="page-title">${listing.title}</h1>
          <div class="deal-head-meta">
            ${platformBadge(listing.platform)}
            ${listing.location ? html`<span class="muted small">${icon('pin', { size: 14 })}${listing.location}</span>` : ''}
            <span class="muted small">${icon('clock', { size: 14 })}İlk görülme ${timeAgo(listing.first_seen)}</span>
            ${listing.date_text ? html`<span class="muted small">İlan tarihi: ${listing.date_text}</span>` : ''}
          </div>
        </div>
        <div class="page-actions" data-actions></div>
      </header>

      <section class="card deal-hero">
        <div class="deal-hero-img">
          ${img ? html`<img src="${img}" alt="" referrerpolicy="no-referrer" data-fallback="remove" />` : ''}
          ${icon('image', { size: 34 })}
        </div>
        <div class="deal-hero-main">
          <div class="deal-hero-top">
            <div>
              <span class="metric-label">İlan fiyatı</span>
              <div class="deal-hero-price">
                <strong>${fmtPrice(listing.price, listing.currency)}</strong>
                ${dropped ? html`<s>${fmtPrice(listing.prev_price, listing.currency)}</s><span class="chip chip-success chip-xs">${icon('trendDown', { size: 12 })}Fiyatı düştü</span>` : ''}
              </div>
            </div>
            <div class="deal-hero-score">
              ${scoreRing(deal.score, { size: 64, label: 'Fırsat puanı' })}
              <span class="muted small">Fırsat puanı</span>
            </div>
          </div>
          <div class="deal-verdict">
            ${deal.is_deal
              ? html`<span class="chip chip-success">${icon('checkCircle', { size: 14 })}Kârlı fırsat</span>`
              : html`<span class="chip">${icon('info', { size: 14 })}Aday — eşikleri geçmedi</span>`}
            ${deal.status !== 'yeni' ? html`<span class="chip chip-accent">${{ favori: 'Favori', incelendi: 'İncelendi', gizli: 'Gizlendi' }[deal.status] || deal.status}</span>` : ''}
          </div>
          <div class="metrics">
            ${metric('Tahmini kâr', fmtSignedPrice(deal.est_profit), { tone: deal.est_profit > 0 ? 'is-pos' : 'is-neg', sub: `${fmtPct(deal.margin_pct)} marj` })}
            ${metric('Piyasa medyanı', fmtPrice(deal.est_value), { sub: `${fmtNum(deal.comps_count)} emsal` })}
            ${metric('Hedef satış', fmtPrice(deal.resale_price), { sub: 'hızlı satış için' })}
            ${metric('Pazarlıklı alış', fmtPrice(deal.buy_price), { sub: 'tahmini' })}
            ${metric('Güven', fmtPct((deal.confidence || 0) * 100), { sub: deal.confidence >= 0.7 ? 'yüksek' : deal.confidence >= 0.4 ? 'orta' : 'düşük' })}
          </div>
        </div>
      </section>

      <div class="deal-detail-grid">
        <div class="stack-lg">
          ${ai ? html`
            <section class="card" aria-labelledby="ai-t">
              <header class="card-head">
                <h2 class="card-title" id="ai-t">${icon('bot', { size: 18 })}Yapay zekâ değerlendirmesi</h2>
                <span class="head-actions">${ai.firsat_mi === true ? html`<span class="chip chip-success">${icon('check', { size: 13 })}Fırsat</span>` : ai.firsat_mi === false ? html`<span class="chip chip-danger">${icon('x', { size: 13 })}Fırsat değil</span>` : ''}</span>
              </header>
              <div class="card-body stack">
                ${ai.yorum ? html`<p class="ai-comment">${ai.yorum}</p>` : ''}
                <div class="metrics metrics-sm">
                  ${isNum(ai.duzeltilmis_piyasa_degeri) && ai.duzeltilmis_piyasa_degeri ? metric('Düzeltilmiş piyasa değeri', fmtPrice(ai.duzeltilmis_piyasa_degeri)) : ''}
                  ${isNum(ai.hizli_satis_fiyati) && ai.hizli_satis_fiyati ? metric('Hızlı satış fiyatı', fmtPrice(ai.hizli_satis_fiyati)) : ''}
                  ${isNum(ai.tahmini_net_kar) ? metric('Tahmini net kâr', fmtSignedPrice(ai.tahmini_net_kar), { tone: ai.tahmini_net_kar > 0 ? 'is-pos' : 'is-neg' }) : ''}
                  ${isNum(ai.pazarlik_teklifi) && ai.pazarlik_teklifi ? metric('Önerilen teklif', fmtPrice(ai.pazarlik_teklifi), { tone: 'is-accent' }) : ''}
                  ${isNum(ai.ayni_urun_emsal_orani) ? metric('Aynı ürün emsal oranı', fmtPct(ai.ayni_urun_emsal_orani * 100)) : ''}
                  ${ai.risk_seviyesi ? metric('Risk seviyesi', html`<span class="chip chip-${(RISK_LEVEL[ai.risk_seviyesi] || RISK_LEVEL.orta).tone}">${(RISK_LEVEL[ai.risk_seviyesi] || { label: ai.risk_seviyesi }).label}</span>`) : ''}
                </div>
                ${(ai.riskler || []).length ? html`
                  <div><h3 class="insight-title">Belirtilen riskler</h3><ul class="insight-list is-bad">${ai.riskler.map((r) => html`<li>${icon('alert', { size: 15 })}<span>${r}</span></li>`)}</ul></div>` : ''}
                ${(ai.kaynaklar || []).length ? html`
                  <div><h3 class="insight-title">Kaynaklar</h3><ul class="source-list">${ai.kaynaklar.map((k) => {
                    const u = safeUrl(k);
                    return html`<li>${u ? html`<a href="${u}" target="_blank" rel="noopener">${icon('link', { size: 14 })}${hostOf(u) || u}</a>` : html`<span>${k}</span>`}</li>`;
                  })}</ul></div>` : ''}
              </div>
            </section>` : ''}

          <section class="card" aria-labelledby="comps-t">
            <header class="card-head">
              <h2 class="card-title" id="comps-t">${icon('list', { size: 18 })}Emsal ilanlar <span class="muted">(${(deal.comps || []).length})</span></h2>
            </header>
            ${(deal.comps || []).length ? html`
              <div class="table-wrap">
                <table class="table">
                  <thead><tr><th scope="col">İlan</th><th scope="col" class="num-col">Fiyat</th><th scope="col" class="num-col">Fark</th><th scope="col">Benzerlik</th></tr></thead>
                  <tbody>
                    ${deal.comps.map((c) => {
                      const u = safeUrl(c.url);
                      const diff = listing.price ? c.price - listing.price : null;
                      return html`<tr>
                        <td class="comp-cell">${u ? html`<a href="${u}" target="_blank" rel="noopener">${c.title}</a>` : c.title}</td>
                        <td class="num-col num">${fmtPrice(c.price)}</td>
                        <td class="num-col num ${diff > 0 ? 'text-success' : diff < 0 ? 'text-danger' : ''}">${diff == null ? '—' : fmtSignedPrice(diff)}</td>
                        <td>${simMeter(c.similarity)}</td>
                      </tr>`;
                    })}
                  </tbody>
                </table>
              </div>
              <p class="card-note muted small">“Fark”, emsalin bu ilandan ne kadar pahalı olduğunu gösterir.</p>` : html`<div class="card-body"><p class="muted">Emsal ilan kaydı yok.</p></div>`}
          </section>

          ${listing.details && (listing.details.description || Object.keys(listing.details.attributes || {}).length) ? html`
            <section class="card" aria-labelledby="det-t">
              <header class="card-head"><h2 class="card-title" id="det-t">${icon('receipt', { size: 18 })}İlan ayrıntıları</h2></header>
              <div class="card-body stack">
                ${Object.keys(listing.details.attributes || {}).length ? html`
                  <dl class="kv">${Object.entries(listing.details.attributes).map(([k, v]) => html`<div><dt>${k}</dt><dd>${v}</dd></div>`)}</dl>` : ''}
                ${listing.details.description ? html`<p class="pre-wrap small">${listing.details.description}</p>` : ''}
              </div>
            </section>` : ''}
        </div>

        <div class="stack-lg">
          ${fastCard(deal.fast)}
          <section class="card" aria-labelledby="why-t">
            <header class="card-head"><h2 class="card-title" id="why-t">${icon('bulb', { size: 18 })}Neden fırsat?</h2></header>
            <div class="card-body">
              ${(deal.reasons || []).length ? html`<ul class="insight-list">${deal.reasons.map((r) => html`<li>${icon('dot', { size: 15 })}<span>${r}</span></li>`)}</ul>` : html`<p class="muted">Gerekçe yok.</p>`}
            </div>
          </section>
          <section class="card" aria-labelledby="risk-t">
            <header class="card-head"><h2 class="card-title" id="risk-t">${icon('shield', { size: 18 })}Riskler</h2></header>
            <div class="card-body">
              ${risks.length ? html`<div class="chips chips-col">${risks.map(riskChip)}</div>` : html`<p class="risk-none">${icon('checkCircle', { size: 18 })}<span>Belirgin bir risk işareti bulunmadı. Yine de alırken ürünü ve belgelerini kontrol edin.</span></p>`}
            </div>
          </section>
          <section class="card" aria-labelledby="hist-t">
            <header class="card-head"><h2 class="card-title" id="hist-t">${icon('history', { size: 18 })}Fiyat geçmişi</h2></header>
            <div class="card-body"><div data-history></div></div>
          </section>
          <p class="muted small center">Son güncelleme ${fmtDateTime(deal.updated_at)}</p>
        </div>
      </div>`.s;
    renderActions();
    mountPriceHistory($('[data-history]', root), data.price_history || [], { currency: listing.currency });
  }

  function renderActions() {
    const { deal, listing } = data;
    const url = safeUrl(listing.url);
    $('[data-actions]', root).innerHTML = html`
      ${url ? html`<a class="btn btn-primary" href="${url}" target="_blank" rel="noopener">${icon('external', { size: 17 })}<span>İlana git</span></a>` : ''}
      <button type="button" class="btn ${deal.status === 'favori' ? 'is-on' : ''}" data-set="favori" aria-pressed="${deal.status === 'favori'}">${icon(deal.status === 'favori' ? 'starFill' : 'star', { size: 17 })}<span>Favori</span></button>
      <button type="button" class="btn ${deal.status === 'incelendi' ? 'is-on' : ''}" data-set="incelendi" aria-pressed="${deal.status === 'incelendi'}">${icon('check', { size: 17 })}<span>İncelendi</span></button>
      ${deal.status === 'gizli'
        ? html`<button type="button" class="btn" data-set="yeni">${icon('eye', { size: 17 })}<span>Geri getir</span></button>`
        : html`<button type="button" class="btn btn-ghost" data-set="gizli">${icon('eyeOff', { size: 17 })}<span>Gizle</span></button>`}`.s;
  }

  async function load() {
    try {
      data = await api(`/api/deals/${id}`, { signal: ctx.signal });
      if (!ctx.alive()) return;
      render();
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      root.innerHTML = e.status === 404
        ? html`<div class="card">${emptyState({ icon: 'search', title: 'Fırsat bulunamadı', text: 'Bu kayıt silinmiş olabilir.', action: html`<a class="btn btn-primary" href="#/firsatlar">Fırsatlara dön</a>` })}</div>`.s
        : html`<div class="card">${errorState(e)}</div>`.s;
    }
  }

  root.addEventListener('click', async (e) => {
    if (e.target.closest('[data-action="retry"]')) {
      load();
      return;
    }
    const b = e.target.closest('[data-set]');
    if (!b || !data) return;
    const prev = data.deal.status;
    let next = b.dataset.set;
    if (next === prev && next !== 'yeni') next = 'yeni';
    b.disabled = true;
    try {
      await setDealStatus(id, next);
      data.deal.status = next;
      render();
      const msgs = { favori: 'Favorilere eklendi.', incelendi: 'İncelendi olarak işaretlendi.', gizli: 'Fırsat gizlendi.', yeni: prev === 'gizli' ? 'Fırsat geri getirildi.' : 'İşaret kaldırıldı.' };
      toast.success(msgs[next] || 'Güncellendi.');
    } catch (err) {
      showError(err);
      b.disabled = false;
    }
  });

  await load();
  return {};
}
