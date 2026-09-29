// Satır içi SVG grafikler: fiyat dağılımı (histogram) ve fiyat geçmişi.
// Kurallar: ince çubuklar (≤24px), 4px yuvarlatılmış uç, kıl çizgisi eksen, seçici etiket,
// fareyle/klavyeyle ipucu ve ekran okuyucular için tablo karşılığı.
import { html, esc, fmtPrice, fmtCompact, fmtDay, fmtDateTime, isNum } from './util.js';
import { bindChartTips } from './ui.js';

const NS = 'http://www.w3.org/2000/svg';

function barPath(x, y, w, h, r = 4) {
  if (h <= 0) return '';
  const rr = Math.min(r, w / 2, h);
  const base = y + h;
  return `M${x},${base}V${y + rr}Q${x},${y} ${x + rr},${y}H${x + w - rr}Q${x + w},${y} ${x + w},${y + rr}V${base}Z`;
}

function observeWidth(container, draw) {
  let lastW = 0;
  const run = () => {
    const w = Math.round(container.clientWidth);
    if (!w || w === lastW) return;
    lastW = w;
    draw(w);
  };
  if ('ResizeObserver' in window) {
    const ro = new ResizeObserver(() => run());
    ro.observe(container);
  } else {
    window.addEventListener('resize', run);
  }
  requestAnimationFrame(run);
  run();
}

/**
 * Fiyat dağılımı histogramı.
 * @param {HTMLElement} container
 * @param {{from:number,to:number,count:number}[]} bins
 * @param {{median?: number, marker?: number, markerLabel?: string, caption?: string}} opts
 */
export function mountHistogram(container, bins, opts = {}) {
  const { median = null, marker = null, markerLabel = 'Sizin fiyatınız', caption = 'Benzer ilanların fiyat dağılımı' } = opts;
  container.classList.add('chart');
  const total = bins.reduce((s, b) => s + (b.count || 0), 0);
  const tableRows = bins.map((b) => html`<tr><td>${fmtPrice(b.from)} – ${fmtPrice(b.to)}</td><td>${b.count}</td></tr>`);
  container.innerHTML = html`
    <figure class="chart-fig">
      <div class="chart-canvas"></div>
      <figcaption class="chart-legend">
        <span class="lg-item"><i class="lg-swatch" aria-hidden="true"></i>İlan sayısı (${total})</span>
        ${isNum(median) ? html`<span class="lg-item"><i class="lg-line lg-median" aria-hidden="true"></i>Medyan ${fmtPrice(median)}</span>` : ''}
        ${isNum(marker) ? html`<span class="lg-item"><i class="lg-line lg-marker" aria-hidden="true"></i>${markerLabel} ${fmtPrice(marker)}</span>` : ''}
      </figcaption>
      <table class="sr-only"><caption>${caption}</caption><thead><tr><th scope="col">Fiyat aralığı</th><th scope="col">İlan sayısı</th></tr></thead><tbody>${tableRows}</tbody></table>
    </figure>`.s;
  const canvas = container.querySelector('.chart-canvas');
  bindChartTips(canvas);
  if (!bins.length) return;

  const lo = bins[0].from;
  const hi = bins[bins.length - 1].to;
  const maxCount = Math.max(1, ...bins.map((b) => b.count || 0));

  observeWidth(canvas, (W) => {
    const H = 168;
    const m = { l: 6, r: 6, t: 22, b: 30 };
    const pw = W - m.l - m.r;
    const ph = H - m.t - m.b;
    const n = bins.length;
    const slot = pw / n;
    const bw = Math.max(6, Math.min(24, slot - 4));
    const base = m.t + ph;
    const xOf = (price) => (hi > lo ? m.l + ((price - lo) / (hi - lo)) * pw : m.l + pw / 2);
    const tallest = bins.reduce((best, b, i) => ((b.count || 0) > (bins[best].count || 0) ? i : best), 0);
    let bars = '';
    let hits = '';
    bins.forEach((b, i) => {
      const cx = m.l + slot * i + slot / 2;
      const h = ((b.count || 0) / maxCount) * ph;
      const x = cx - bw / 2;
      const y = base - h;
      bars += `<path class="hist-bar" d="${barPath(x, y, bw, h)}"/>`;
      if (i === tallest && b.count) {
        bars += `<text class="chart-label" x="${cx}" y="${Math.max(12, y - 6)}" text-anchor="middle">${b.count}</text>`;
      }
      const range = b.from === b.to ? fmtPrice(b.from) : `${fmtPrice(b.from)} – ${fmtPrice(b.to)}`;
      hits += `<rect class="hit" x="${m.l + slot * i}" y="${m.t - 10}" width="${slot}" height="${ph + 10}" tabindex="0" role="img" aria-label="${esc(range)}: ${b.count} ilan" data-tip-value="${b.count} ilan" data-tip-label="${esc(range)}"/>`;
    });
    let refs = '';
    if (isNum(median) && hi > lo) {
      const x = Math.round(xOf(Math.min(hi, Math.max(lo, median)))) + 0.5;
      refs += `<line class="ref-median" x1="${x}" x2="${x}" y1="${m.t - 8}" y2="${base}"/>`;
    }
    if (isNum(marker) && hi > lo) {
      const inRange = marker >= lo && marker <= hi;
      const x = Math.round(xOf(Math.min(hi, Math.max(lo, marker)))) + 0.5;
      refs += `<line class="ref-marker${inRange ? '' : ' is-out'}" x1="${x}" x2="${x}" y1="${m.t - 8}" y2="${base}"/>`;
    }
    const labels = [
      `<text class="chart-axis-label" x="${m.l}" y="${H - 8}" text-anchor="start">${esc(fmtCompact(lo))}</text>`,
      `<text class="chart-axis-label" x="${W - m.r}" y="${H - 8}" text-anchor="end">${esc(fmtCompact(hi))}</text>`,
    ];
    if (W >= 360 && hi > lo) {
      labels.push(`<text class="chart-axis-label" x="${m.l + pw / 2}" y="${H - 8}" text-anchor="middle">${esc(fmtCompact((lo + hi) / 2))}</text>`);
    }
    canvas.innerHTML = `
      <svg xmlns="${NS}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="${esc(caption)}">
        <line class="chart-baseline" x1="${m.l}" x2="${W - m.r}" y1="${base + 0.5}" y2="${base + 0.5}"/>
        ${bars}
        ${refs}
        ${labels.join('')}
        ${hits}
      </svg>`;
  });
}

/**
 * Fiyat geçmişi çizgi grafiği.
 * @param {HTMLElement} container
 * @param {{price:number, seen_at:string}[]} points
 */
export function mountPriceHistory(container, points, { currency = 'TL' } = {}) {
  container.classList.add('chart');
  const pts = (points || []).filter((p) => isNum(p.price)).map((p) => ({ ...p, t: new Date(p.seen_at).getTime() }));
  container.innerHTML = html`
    <figure class="chart-fig">
      <div class="chart-canvas"></div>
      <table class="sr-only"><caption>Fiyat geçmişi</caption><thead><tr><th scope="col">Tarih</th><th scope="col">Fiyat</th></tr></thead>
        <tbody>${pts.map((p) => html`<tr><td>${fmtDateTime(p.seen_at)}</td><td>${fmtPrice(p.price, currency)}</td></tr>`)}</tbody></table>
    </figure>`.s;
  const canvas = container.querySelector('.chart-canvas');
  bindChartTips(canvas);
  if (!pts.length) {
    canvas.innerHTML = html`<p class="muted small">Fiyat geçmişi yok.</p>`.s;
    return;
  }
  observeWidth(canvas, (W) => {
    const H = 150;
    const m = { l: 10, r: 10, t: 26, b: 28 };
    const pw = W - m.l - m.r;
    const ph = H - m.t - m.b;
    const prices = pts.map((p) => p.price);
    let yMin = Math.min(...prices);
    let yMax = Math.max(...prices);
    if (yMax === yMin) {
      yMin -= yMin * 0.05 || 1;
      yMax += yMax * 0.05 || 1;
    } else {
      const pad = (yMax - yMin) * 0.25;
      yMin -= pad;
      yMax += pad;
    }
    const t0 = pts[0].t;
    const t1 = pts[pts.length - 1].t;
    const xOf = (p, i) => (t1 > t0 ? m.l + ((p.t - t0) / (t1 - t0)) * pw : pts.length > 1 ? m.l + (i / (pts.length - 1)) * pw : m.l + pw / 2);
    const yOf = (v) => m.t + (1 - (v - yMin) / (yMax - yMin)) * ph;
    const xy = pts.map((p, i) => [xOf(p, i), yOf(p.price)]);
    // Fiyat ilan sitesinde basamaklı değişir: adım çizgisi kullan.
    let d = `M${xy[0][0]},${xy[0][1]}`;
    for (let i = 1; i < xy.length; i++) d += `H${xy[i][0]}V${xy[i][1]}`;
    if (xy.length === 1) d = `M${m.l},${xy[0][1]}H${W - m.r}`;
    const lastX = xy.length === 1 ? W - m.r : xy[xy.length - 1][0];
    const area = `${d}H${lastX}V${m.t + ph}H${xy.length === 1 ? m.l : xy[0][0]}Z`;
    const dots = xy.map(([x, y], i) => `<circle class="line-dot" cx="${x}" cy="${y}" r="4"/>` +
      `<circle class="hit" cx="${x}" cy="${y}" r="14" tabindex="0" role="img" aria-label="${esc(fmtDateTime(pts[i].seen_at))}: ${esc(fmtPrice(pts[i].price, currency))}" data-tip-value="${esc(fmtPrice(pts[i].price, currency))}" data-tip-label="${esc(fmtDateTime(pts[i].seen_at))}"/>`).join('');
    const last = pts[pts.length - 1];
    const [lx, ly] = xy[xy.length - 1];
    const labelAnchor = lx > W - 80 ? 'end' : 'middle';
    const firstLabel = pts.length > 1 && pts[0].price !== last.price
      ? `<text class="chart-label muted" x="${Math.max(m.l, xy[0][0])}" y="${xy[0][1] - 10}" text-anchor="start">${esc(fmtPrice(pts[0].price, currency))}</text>` : '';
    canvas.innerHTML = `
      <svg xmlns="${NS}" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="group" aria-label="Fiyat geçmişi">
        <line class="chart-baseline" x1="${m.l}" x2="${W - m.r}" y1="${m.t + ph + 0.5}" y2="${m.t + ph + 0.5}"/>
        <path class="line-area" d="${area}"/>
        <path class="line-path" d="${d}"/>
        ${firstLabel}
        <text class="chart-label" x="${lx}" y="${ly - 10}" text-anchor="${labelAnchor}">${esc(fmtPrice(last.price, currency))}</text>
        ${dots}
        <text class="chart-axis-label" x="${m.l}" y="${H - 8}" text-anchor="start">${esc(fmtDay(pts[0].seen_at))}</text>
        ${pts.length > 1 ? `<text class="chart-axis-label" x="${W - m.r}" y="${H - 8}" text-anchor="end">${esc(fmtDay(last.seen_at))}</text>` : ''}
      </svg>`;
  });
}

/** Benzerlik göstergesi (0–1). */
export function simMeter(sim) {
  const pct = Math.round(Math.max(0, Math.min(1, Number(sim) || 0)) * 100);
  return html`<span class="sim" title="Benzerlik %${pct}"><span class="sim-track" aria-hidden="true"><span class="sim-fill" style="width:${pct}%"></span></span><span class="sim-val">%${pct}</span></span>`;
}
