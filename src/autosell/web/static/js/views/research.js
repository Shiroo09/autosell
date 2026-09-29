// Fiyat araştırması: bir ürün için piyasadaki benzer ilanları tarayıp fiyat önerir.
import { api, enc } from '../api.js';
import { html, $, $$, fmtRel, safeUrl, store, platformName } from '../util.js';
import { icon } from '../icons.js';
import { toast, showError, setBusy } from '../ui.js';
import { replaceQuery } from '../router.js';
import { jobCard, trackJob, isActive } from '../jobs.js';
import { researchResult } from '../research.js';

const RECENT_KEY = 'research.recent';

export async function mount(root, ctx) {
  let platform = store.get('research.platform', 'sahibinden');
  let mode = 'query';
  let card = null;
  const recent = store.get(RECENT_KEY, []);

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">Fiyat Araştırması</h1>
        <p class="page-sub">Bir ürünün piyasa değerini benzer ilanlardan hesaplayın: medyan, tipik aralık ve satış önerileri.</p>
      </div>
    </header>
    <section class="card research-form-card">
      <form class="card-body stack" data-form novalidate>
        <div class="research-form-top">
          <div class="field">
            <span class="label" id="rs-plat-l">Platform</span>
            <div class="segmented" role="radiogroup" aria-labelledby="rs-plat-l">
              ${['sahibinden', 'letgo'].map((p) => html`<label><input type="radio" name="platform" value="${p}" ${platform === p ? 'checked' : ''} /><span class="seg"><i class="pdot pdot-${p}"></i>${platformName(p)}</span></label>`)}
            </div>
          </div>
          <div class="field">
            <span class="label" id="rs-mode-l">Arama türü</span>
            <div class="segmented" role="radiogroup" aria-labelledby="rs-mode-l">
              <label><input type="radio" name="mode" value="query" checked /><span class="seg">${icon('search', { size: 16 })}Kelime</span></label>
              <label><input type="radio" name="mode" value="url" /><span class="seg">${icon('link', { size: 16 })}Bağlantı</span></label>
            </div>
          </div>
        </div>
        <div class="field" data-mode="query">
          <label class="label" for="rs-q">Ürün</label>
          <div class="input-row">
            <div class="input-wrap has-prefix grow">
              <span class="input-prefix">${icon('search', { size: 18 })}</span>
              <input id="rs-q" class="input" name="query" type="text" placeholder="ör. iPhone 13 128 GB" autocomplete="off" enterkeyhint="search" />
            </div>
          </div>
          <p class="hint">Marka ve model yeterli; renk gibi fiyatı az etkileyen ayrıntıları eklemeyin.</p>
        </div>
        <div class="field" data-mode="url" hidden>
          <label class="label" for="rs-url">Arama bağlantısı</label>
          <input id="rs-url" class="input" name="url" type="url" inputmode="url" placeholder="https://www.sahibinden.com/..." autocomplete="off" />
          <p class="hint">Sitede aramanızı ve süzgeçlerinizi yapıp adres çubuğundaki bağlantıyı yapıştırın; en isabetli sonuç böyle alınır.</p>
        </div>
        <div class="research-submit">
          <button type="submit" class="btn btn-primary btn-lg" data-submit>${icon('chart', { size: 18 })}<span>Araştır</span></button>
          <p class="hint">AutoSell'in çalıştığı bilgisayarda bir tarayıcı açılıp arama sonuçları okunur; genellikle 20–60 saniye sürer.</p>
        </div>
        <div class="recent" data-recent></div>
      </form>
    </section>
    <div class="job-stack" data-job></div>
    <section data-result aria-live="polite"></section>`.s;

  const form = $('[data-form]', root);
  const $job = $('[data-job]', root);
  const $result = $('[data-result]', root);
  const submitBtn = $('[data-submit]', root);

  function renderRecent() {
    const box = $('[data-recent]', root);
    if (!recent.length) {
      box.innerHTML = '';
      return;
    }
    box.innerHTML = html`
      <span class="muted small">Son aramalar:</span>
      <div class="chips">${recent.slice(0, 6).map((r, i) => html`<button type="button" class="chip chip-add" data-recent-i="${i}"><i class="pdot pdot-${r.platform}"></i><span>${r.query || r.url}</span></button>`)}</div>`.s;
  }

  function remember(entry) {
    const key = `${entry.platform}|${entry.query}|${entry.url}`;
    const i = recent.findIndex((r) => `${r.platform}|${r.query}|${r.url}` === key);
    if (i >= 0) recent.splice(i, 1);
    recent.unshift(entry);
    recent.length = Math.min(recent.length, 8);
    store.set(RECENT_KEY, recent);
    renderRecent();
  }

  function showResult(job) {
    $result.replaceChildren();
    if (!job || job.status !== 'done' || !job.result) return;
    const wrap = document.createElement('div');
    wrap.className = 'card research-result-card';
    const head = document.createElement('header');
    head.className = 'card-head';
    head.innerHTML = html`
      <h2 class="card-title">${icon('chart', { size: 18 })}Sonuçlar</h2>
      <span class="head-actions muted small">${job.finished_at ? fmtRel(job.finished_at) : ''}</span>`.s;
    const body = document.createElement('div');
    body.className = 'card-body';
    body.appendChild(researchResult(job.result, { showRisky: true }));
    wrap.append(head, body);
    $result.appendChild(wrap);
  }

  function attach(job) {
    if (card) card.stop();
    $job.replaceChildren();
    card = jobCard(job, {
      onUpdate: (j) => {
        if (isActive(j)) setBusy(submitBtn, true, 'Araştırılıyor…');
      },
      onDone: (j) => {
        setBusy(submitBtn, false);
        showResult(j);
        if (j.status === 'done') {
          const n = (j.result && j.result.matched) || 0;
          if (n) toast.success(`${n} benzer ilan bulundu.`, { title: 'Araştırma tamamlandı' });
        }
      },
    });
    $job.appendChild(card.el);
    if (isActive(job)) setBusy(submitBtn, true, 'Araştırılıyor…');
  }

  form.addEventListener('change', (e) => {
    if (e.target.name === 'platform') {
      platform = e.target.value;
      store.set('research.platform', platform);
    }
    if (e.target.name === 'mode') {
      mode = e.target.value;
      $$('[data-mode]', form).forEach((x) => (x.hidden = x.dataset.mode !== mode));
      $(mode === 'url' ? '#rs-url' : '#rs-q', form).focus();
    }
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const query = $('#rs-q', form).value.trim();
    const url = $('#rs-url', form).value.trim();
    const payload = { platform, query: mode === 'query' ? query : '', url: mode === 'url' ? url : '' };
    if (mode === 'query' && !query) {
      $('#rs-q', form).focus();
      toast.error('Araştırılacak ürünü yazın.');
      return;
    }
    if (mode === 'url' && !safeUrl(url)) {
      $('#rs-url', form).focus();
      toast.error('Geçerli bir arama bağlantısı yapıştırın.');
      return;
    }
    setBusy(submitBtn, true, 'Başlatılıyor…');
    try {
      const job = await api.post('/api/research', payload);
      trackJob(job);
      remember(payload);
      replaceQuery({ is: job.id });
      $result.replaceChildren();
      attach(job);
    } catch (err) {
      setBusy(submitBtn, false);
      showError(err);
    }
  });

  root.addEventListener('click', (e) => {
    const r = e.target.closest('[data-recent-i]');
    if (!r) return;
    const item = recent[Number(r.dataset.recentI)];
    if (!item) return;
    platform = item.platform;
    $(`input[name="platform"][value="${item.platform}"]`, form).checked = true;
    mode = item.url ? 'url' : 'query';
    $(`input[name="mode"][value="${mode}"]`, form).checked = true;
    $$('[data-mode]', form).forEach((x) => (x.hidden = x.dataset.mode !== mode));
    $('#rs-q', form).value = item.query || '';
    $('#rs-url', form).value = item.url || '';
    form.requestSubmit ? form.requestSubmit() : form.dispatchEvent(new Event('submit', { cancelable: true }));
  });

  renderRecent();

  // Önceki araştırmayı göster: adres çubuğundaki iş ya da son bağımsız araştırma
  const qJob = ctx.query.get('is');
  const prefill = ctx.query.get('q');
  if (prefill) $('#rs-q', form).value = prefill;
  try {
    let job = null;
    if (qJob) job = await api(`/api/jobs/${enc(qJob)}`).catch(() => null);
    if (!job) {
      const jobs = await api('/api/jobs?limit=60', { signal: ctx.signal });
      job = jobs.find((j) => j.kind === 'research' && !j.draft_id) || null;
    }
    if (job && ctx.alive()) {
      if (job.result && job.result.query) $('#rs-q', form).value = job.result.query;
      if (job.platform) {
        platform = job.platform;
        const radio = $(`input[name="platform"][value="${job.platform}"]`, form);
        if (radio) radio.checked = true;
      }
      attach(job);
    }
  } catch (e) {
    if (e.name !== 'AbortError') showError(e);
  }

  ctx.scope.cleanup(() => card && card.stop());
  return {};
}
