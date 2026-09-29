// Fiyat araştırması sonuçları (düzenleyici ve araştırma sayfası ortak kullanır).
import { html, el, $, fmtPrice, fmtNum, fmtPct, safeUrl, hostOf, platformName, isNum } from './util.js';
import { icon } from './icons.js';
import { mountHistogram, simMeter } from './charts.js';
import { emptyState, platformBadge } from './ui.js';

const SUGGESTIONS = [
  { key: 'quick', title: 'Hızlı satış', text: 'Birkaç gün içinde satmak için; piyasanın alt çeyreğinin biraz altı.', icon: 'zap' },
  { key: 'fair', title: 'Piyasa fiyatı', text: 'Benzer ilanların ortası (medyan). Dengeli seçim.', icon: 'scale' },
  { key: 'high', title: 'Üst fiyat', text: 'Acele etmiyorsanız; pazarlık payı bırakır.', icon: 'trendUp' },
];

/**
 * @param {object} result  scanner.research() çıktısı
 * @param {{onUsePrice?: (price:number)=>void, currentPrice?: number|null, showRisky?: boolean, compact?: boolean}} opts
 * @returns {HTMLElement}
 */
export function researchResult(result, opts = {}) {
  const { onUsePrice = null, currentPrice = null, showRisky = true, compact = false } = opts;
  const est = (result && result.estimate) || {};
  const sug = (result && result.suggestions) || {};
  const comps = est.comps || [];
  const matched = result ? result.matched || 0 : 0;
  const scanned = result ? result.scanned || 0 : 0;
  const conf = Math.round((est.confidence || 0) * 100);
  const confLabel = conf >= 70 ? 'Yüksek' : conf >= 40 ? 'Orta' : 'Düşük';
  const query = result && (result.query || result.url);

  const node = el(html`<section class="research ${compact ? 'is-compact' : ''}" aria-label="Fiyat araştırması sonuçları"></section>`);
  if (!matched) {
    node.innerHTML = html`
      <div class="research-head">
        ${result && result.platform ? platformBadge(result.platform) : ''}
        ${query ? html`<span class="research-q" title="${query}">“${query}”</span>` : ''}
        <span class="muted small">${fmtNum(scanned)} ilan tarandı</span>
      </div>
      ${emptyState({
        icon: 'search',
        title: 'Yeterli benzer ilan bulunamadı',
        text: scanned ? 'Taranan ilanlar ürüne yeterince benzemiyordu. Aramayı sadeleştirin (ör. yalnızca marka ve model) ya da sitede filtrelediğiniz arama bağlantısını kullanın.' : 'Sayfada ilan okunamadı. Arama bağlantısını kontrol edin ya da başka bir kelimeyle deneyin.',
      })}`.s;
    return node;
  }

  node.innerHTML = html`
    <div class="research-head">
      ${result.platform ? platformBadge(result.platform) : ''}
      ${query ? html`<span class="research-q" title="${query}">“${query}”</span>` : ''}
      <span class="muted small">${fmtNum(scanned)} ilan tarandı · ${fmtNum(matched)} benzer</span>
    </div>

    <div class="research-stats">
      <div class="rstat rstat-main">
        <span class="rstat-label">Piyasa medyanı</span>
        <strong class="rstat-value">${fmtPrice(est.median)}</strong>
        <span class="rstat-sub">${fmtNum(matched)} benzer ilana göre</span>
      </div>
      <div class="rstat">
        <span class="rstat-label">Tipik aralık</span>
        <strong class="rstat-value sm">${fmtPrice(est.p25)} – ${fmtPrice(est.p75)}</strong>
        <span class="rstat-sub">İlanların yarısı bu aralıkta</span>
      </div>
      <div class="rstat">
        <span class="rstat-label">En düşük / en yüksek</span>
        <strong class="rstat-value sm">${fmtPrice(est.low)} – ${fmtPrice(est.high)}</strong>
        <span class="rstat-sub">Aykırı fiyatlar ayıklandı</span>
      </div>
      <div class="rstat">
        <span class="rstat-label">Güven</span>
        <strong class="rstat-value sm">${confLabel} <span class="muted">(${fmtPct(conf)})</span></strong>
        <span class="rstat-sub">Benzerlik ${fmtPct((est.mean_similarity || 0) * 100)}</span>
      </div>
    </div>

    <div class="suggest-grid">
      ${SUGGESTIONS.map((s) => {
        const v = sug[s.key];
        const isCurrent = isNum(currentPrice) && isNum(v) && Math.round(currentPrice) === Math.round(v);
        return html`
          <div class="suggest ${s.key === 'fair' ? 'is-featured' : ''}">
            <div class="suggest-top">
              <span class="suggest-icon">${icon(s.icon, { size: 16 })}</span>
              <span class="suggest-title">${s.title}</span>
              ${s.key === 'fair' ? html`<span class="chip chip-accent chip-xs">Önerilen</span>` : ''}
            </div>
            <strong class="suggest-price">${fmtPrice(v)}</strong>
            <p class="suggest-text">${s.text}</p>
            ${onUsePrice && isNum(v) ? html`
              <button type="button" class="btn btn-sm ${s.key === 'fair' ? 'btn-primary' : ''}" data-use-price="${v}" ${isCurrent ? 'disabled' : ''}>
                ${isCurrent ? html`${icon('check', { size: 16 })}<span>Kullanılıyor</span>` : 'Bu fiyatı kullan'}
              </button>` : ''}
          </div>`;
      })}
    </div>

    ${(result.histogram || []).length ? html`
      <div class="research-block">
        <h4 class="block-title">Fiyat dağılımı</h4>
        <div class="hist-host"></div>
      </div>` : ''}

    ${comps.length ? html`
      <div class="research-block">
        <h4 class="block-title">Benzer ilanlar <span class="muted">(${comps.length})</span></h4>
        <ul class="comps">
          ${comps.slice(0, compact ? 8 : 40).map((c) => {
            const url = safeUrl(c.url);
            return html`
              <li class="comp">
                <div class="comp-main">
                  ${url ? html`<a href="${url}" target="_blank" rel="noopener" class="comp-title">${c.title}</a>` : html`<span class="comp-title">${c.title}</span>`}
                  ${simMeter(c.similarity)}
                </div>
                <strong class="comp-price">${fmtPrice(c.price)}</strong>
              </li>`;
          })}
        </ul>
        ${compact && comps.length > 8 ? html`<p class="muted small">+${comps.length - 8} ilan daha</p>` : ''}
      </div>` : ''}

    ${showRisky && (result.risky || []).length ? html`
      <div class="research-block">
        <h4 class="block-title">${icon('alert', { size: 16 })} Dikkat gerektiren ilanlar</h4>
        <p class="muted small">Bu ilanlar fiyat hesabına katıldı ancak risk işaretleri taşıyor.</p>
        <ul class="comps">
          ${result.risky.map((r) => {
            const url = safeUrl(r.url);
            return html`
              <li class="comp is-risky">
                <div class="comp-main">
                  ${url ? html`<a href="${url}" target="_blank" rel="noopener" class="comp-title">${r.title}</a>` : html`<span class="comp-title">${r.title}</span>`}
                  <div class="chips">${(r.risks || []).map((t) => html`<span class="chip chip-orange chip-wrap">${icon('alert', { size: 12 })}<span>${t}</span></span>`)}</div>
                </div>
                <strong class="comp-price">${fmtPrice(r.price)}</strong>
              </li>`;
          })}
        </ul>
      </div>` : ''}
  `.s;

  const host = $('.hist-host', node);
  if (host) {
    mountHistogram(host, result.histogram || [], {
      median: est.median,
      marker: isNum(currentPrice) ? currentPrice : null,
      caption: `${platformName(result.platform)} fiyat dağılımı`,
    });
  }
  if (onUsePrice) {
    node.addEventListener('click', (e) => {
      const b = e.target.closest('[data-use-price]');
      if (b) onUsePrice(Number(b.dataset.usePrice));
    });
  }
  return node;
}

export function researchHost(url) {
  return hostOf(url);
}
