// Takip listeleri: aranan ürünleri düzenli tarayan kayıtlar; oluşturma, düzenleme ve anlık tarama.
import { api } from '../api.js';
import { html, el, $, $$, fmtPrice, fmtNum, fmtPct, fmtRel, timeAgo, parsePrice, priceInputValue, safeUrl, hostOf, platformName, isNum } from '../util.js';
import { icon } from '../icons.js';
import { toast, showError, openSheet, confirmDialog, emptyState, errorState, setBusy, skeletonCards, spinner } from '../ui.js';
import { replaceQuery } from '../router.js';
import { trackJob, watchJob, friendlyError, openJobsDrawer } from '../jobs.js';

const splitWords = (s) => String(s || '').split(',').map((w) => w.trim()).filter(Boolean);

export async function mount(root, ctx) {
  let watches = null;
  let minInterval = 5;
  const runners = new Map(); // watch id → { job, stop }
  const lastLog = new Map();

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">Takip Listeleri</h1>
        <p class="page-sub">Aradığınız ürünleri düzenli tarar, piyasanın altındaki ilanları fırsat olarak işaretler.</p>
      </div>
      <div class="page-actions">
        <button type="button" class="btn btn-primary" data-new>${icon('plus', { size: 18, strokeWidth: 2.2 })}<span>Yeni takip</span></button>
      </div>
    </header>
    <div class="watch-grid" data-list aria-live="polite">${skeletonCards(3, 'skel-watch')}</div>`.s;

  const $list = $('[data-list]', root);

  api('/api/settings', { signal: ctx.signal }).then((s) => {
    if (s && s.market) minInterval = s.market.min_interval_min || 5;
  }).catch(() => {});

  function summary(w) {
    const parts = [];
    if (isNum(w.price_min) || isNum(w.price_max)) {
      parts.push(isNum(w.price_min) && isNum(w.price_max) ? `${fmtPrice(w.price_min)} – ${fmtPrice(w.price_max)}`
        : isNum(w.price_max) ? `≤ ${fmtPrice(w.price_max)}` : `≥ ${fmtPrice(w.price_min)}`);
    }
    parts.push(`min kâr ${fmtPrice(w.min_profit)}`);
    parts.push(`min marj ${fmtPct(w.min_margin_pct)}`);
    parts.push(`her ${fmtNum(w.interval_min)} dk`);
    return parts;
  }

  function card(w) {
    const run = runners.get(w.id);
    const running = !!(run || w.running_job);
    const isError = /^hata/i.test(w.last_status || '');
    const url = safeUrl(w.search_url);
    const log = lastLog.get(w.id);
    return html`
      <article class="watch-card card ${w.active ? '' : 'is-paused'}" data-watch="${w.id}">
        <div class="watch-top">
          <div class="watch-titles">
            <h2 class="watch-name">${w.name}</h2>
            <div class="watch-query">
              <span class="pbadge"><i class="pdot pdot-${w.platform}"></i>${platformName(w.platform)}</span>
              ${url ? html`<a href="${url}" target="_blank" rel="noopener" class="watch-url" title="${url}">${icon('link', { size: 14 })}${hostOf(url)}${new URL(url).pathname.length > 1 ? '/…' : ''}</a>` : html`<span class="watch-q">“${w.query}”</span>`}
            </div>
          </div>
          <label class="switch is-compact" title="${w.active ? 'Otomatik tarama açık' : 'Otomatik tarama kapalı'}">
            <input type="checkbox" data-active ${w.active ? 'checked' : ''} aria-label="${w.name} otomatik taransın" />
            <span class="switch-track" aria-hidden="true"></span>
            <span class="switch-text"><span class="switch-label">${w.active ? 'Aktif' : 'Durduruldu'}</span></span>
          </label>
        </div>
        <div class="chips">${summary(w).map((t) => html`<span class="chip">${t}</span>`)}</div>
        ${(w.include_words || []).length || (w.exclude_words || []).length ? html`
          <p class="watch-words small">
            ${(w.include_words || []).length ? html`<span><span class="muted">İçermeli:</span> ${w.include_words.join(', ')}</span>` : ''}
            ${(w.exclude_words || []).length ? html`<span><span class="muted">Hariç:</span> ${w.exclude_words.join(', ')}</span>` : ''}
          </p>` : ''}
        <div class="watch-status ${isError ? 'is-error' : ''}">
          ${running ? html`
            <div class="watch-running">
              <span class="row">${spinner(14)}<strong>Taranıyor…</strong><button type="button" class="link-btn small" data-job-open="${run ? run.job.id : w.running_job}">Ayrıntılar</button></span>
              ${log ? html`<span class="muted small watch-log">${log}</span>` : ''}
              <div class="progress"><span></span></div>
            </div>` : w.last_run_at ? html`
            <span class="watch-last">${icon(isError ? 'alert' : 'checkCircle', { size: 16 })}<span><strong>Son tarama ${fmtRel(w.last_run_at)}</strong>${w.last_status ? html` · ${isError ? friendlyError(w.last_status.replace(/^Hata:\s*/i, '')) : w.last_status}` : ''}</span></span>` : html`
            <span class="watch-last muted">${icon('clock', { size: 16 })}<span>Henüz taranmadı${w.active ? ' · ilk tarama birazdan' : ''}</span></span>`}
        </div>
        <div class="watch-actions">
          <button type="button" class="btn btn-sm btn-soft" data-scan ${running ? 'disabled' : ''}>${icon('play', { size: 15 })}<span>Şimdi tara</span></button>
          <a class="btn btn-sm" href="#/firsatlar?watch=${w.id}">${icon('target', { size: 15 })}<span>Fırsatlar${w.last_found ? ` (${w.last_found})` : ''}</span></a>
          <span class="grow"></span>
          <button type="button" class="btn btn-sm btn-ghost" data-edit aria-label="${w.name} düzenle">${icon('pencil', { size: 16 })}<span class="hide-xs">Düzenle</span></button>
          <button type="button" class="btn btn-sm btn-ghost btn-danger btn-icon" data-delete aria-label="${w.name} sil" title="Sil">${icon('trash', { size: 16 })}</button>
        </div>
      </article>`;
  }

  function render() {
    if (!watches) return;
    if (!watches.length) {
      $list.className = 'watch-grid is-empty';
      $list.innerHTML = html`<div class="card">${emptyState({
        icon: 'eye',
        title: 'Henüz takip listeniz yok',
        text: 'Almak istediğiniz ürünü (ör. “iPhone 13 128 GB”) ekleyin. AutoSell aramayı düzenli tarar, fiyatları emsallerle karşılaştırır ve kârlı ilanları fırsat olarak işaretler.',
        action: html`<button type="button" class="btn btn-primary btn-lg" data-new>${icon('plus', { size: 18 })}<span>İlk takibi ekle</span></button>`,
      })}</div>`.s;
      return;
    }
    $list.className = 'watch-grid';
    $list.innerHTML = html`${watches.map(card)}`.s;
  }

  function rerenderCard(id) {
    const w = watches && watches.find((x) => x.id === id);
    const node = $(`[data-watch="${id}"]`, $list);
    if (w && node) node.replaceWith(el(card(w)));
  }

  async function load() {
    try {
      const data = await api('/api/watches', { signal: ctx.signal });
      if (!ctx.alive()) return;
      watches = data;
      for (const w of watches) if (w.running_job && !runners.has(w.id)) follow(w.id, { id: w.running_job, status: 'running' });
      render();
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      if (!watches) {
        $list.className = 'watch-grid is-empty';
        $list.innerHTML = html`<div class="card">${errorState(e)}</div>`.s;
      }
    }
  }

  function follow(watchId, job) {
    if (runners.has(watchId)) return;
    const w = watchJob(job.id, (j) => {
      if (!j) {
        runners.delete(watchId);
        load();
        return;
      }
      const last = (j.logs || []).slice(-1)[0];
      if (last) lastLog.set(watchId, last.msg);
      runners.set(watchId, { job: j, stop: w.stop });
      if (!['queued', 'running', 'waiting'].includes(j.status)) {
        runners.delete(watchId);
        lastLog.delete(watchId);
        const name = (watches.find((x) => x.id === watchId) || {}).name || 'Takip';
        if (j.status === 'done') {
          const r = j.result || {};
          toast.success(r.message || 'Tarama tamamlandı.', {
            title: `${name}: tarama bitti`,
            action: r.deals ? { label: `${r.deals} fırsat`, href: `#/firsatlar?watch=${watchId}` } : null,
          });
        } else if (j.status === 'error') {
          toast.error(friendlyError(j.error), { title: `${name}: tarama başarısız` });
        }
        load();
        return;
      }
      rerenderCard(watchId);
    });
    runners.set(watchId, { job, stop: w.stop });
  }

  // ---------------------------------------------------------------- form
  function openForm(existing = null) {
    const w = existing || { name: '', platform: 'sahibinden', query: '', search_url: '', price_min: null, price_max: null, include_words: [], exclude_words: [], min_profit: 1000, min_margin_pct: 12, interval_min: 15, active: true };
    let mode = w.search_url ? 'url' : 'query';
    const sheet = openSheet({
      title: existing ? 'Takibi düzenle' : 'Yeni takip listesi',
      subtitle: existing ? w.name : 'Aradığınız ürünü tanımlayın; AutoSell düzenli tarasın.',
      icon: 'eye',
      size: 'md',
      body: html`
        <form class="watch-form stack" novalidate id="watch-form">
          <div class="field">
            <label class="label" for="wf-name">Liste adı</label>
            <input id="wf-name" class="input" name="name" type="text" required value="${w.name}" placeholder="ör. iPhone 13 fırsatları" autocomplete="off" ${existing ? '' : 'autofocus'} />
          </div>
          <div class="field">
            <span class="label" id="wf-plat-l">Platform</span>
            <div class="segmented is-block" role="radiogroup" aria-labelledby="wf-plat-l">
              ${['sahibinden', 'letgo'].map((p) => html`<label><input type="radio" name="platform" value="${p}" ${w.platform === p ? 'checked' : ''} /><span class="seg"><i class="pdot pdot-${p}"></i>${platformName(p)}</span></label>`)}
            </div>
          </div>
          <div class="field">
            <span class="label" id="wf-mode-l">Ne aranacak?</span>
            <div class="segmented is-block" role="radiogroup" aria-labelledby="wf-mode-l">
              <label><input type="radio" name="mode" value="query" ${mode === 'query' ? 'checked' : ''} /><span class="seg">${icon('search', { size: 16 })}Arama kelimesi</span></label>
              <label><input type="radio" name="mode" value="url" ${mode === 'url' ? 'checked' : ''} /><span class="seg">${icon('link', { size: 16 })}Arama bağlantısı</span></label>
            </div>
          </div>
          <div class="field" data-mode="query" ${mode === 'query' ? '' : 'hidden'}>
            <label class="label" for="wf-query">Arama kelimesi</label>
            <input id="wf-query" class="input" name="query" type="text" value="${w.query}" placeholder="ör. iPhone 13 128 GB" autocomplete="off" />
            <p class="hint">Marka, model ve kapasite gibi ürünü net tanımlayan kelimeler kullanın.</p>
          </div>
          <div class="field" data-mode="url" ${mode === 'url' ? '' : 'hidden'}>
            <label class="label" for="wf-url">Arama bağlantısı</label>
            <input id="wf-url" class="input" name="search_url" type="url" inputmode="url" value="${w.search_url}" placeholder="https://www.sahibinden.com/..." autocomplete="off" />
            <p class="hint">${icon('bulb', { size: 14 })} En güvenilir yol: sitede aramanızı yapıp fiyat, konum, durum gibi süzgeçleri seçin; ardından adres çubuğundaki bağlantıyı kopyalayıp buraya yapıştırın.</p>
          </div>
          <div class="grid-2">
            <div class="field">
              <label class="label" for="wf-pmin">En düşük fiyat <span class="opt">(isteğe bağlı)</span></label>
              <div class="input-wrap"><input id="wf-pmin" class="input input-price" name="price_min" type="text" inputmode="numeric" value="${priceInputValue(w.price_min)}" placeholder="—" /><span class="input-suffix">TL</span></div>
            </div>
            <div class="field">
              <label class="label" for="wf-pmax">En yüksek fiyat <span class="opt">(isteğe bağlı)</span></label>
              <div class="input-wrap"><input id="wf-pmax" class="input input-price" name="price_max" type="text" inputmode="numeric" value="${priceInputValue(w.price_max)}" placeholder="—" /><span class="input-suffix">TL</span></div>
            </div>
          </div>
          <div class="grid-2">
            <div class="field">
              <label class="label" for="wf-profit">En az kâr</label>
              <div class="input-wrap"><input id="wf-profit" class="input input-price" name="min_profit" type="text" inputmode="numeric" value="${priceInputValue(w.min_profit)}" /><span class="input-suffix">TL</span></div>
              <p class="hint">Bunun altındaki kârlar fırsat sayılmaz.</p>
            </div>
            <div class="field">
              <label class="label" for="wf-margin">En az marj</label>
              <div class="input-wrap"><input id="wf-margin" class="input" name="min_margin_pct" type="number" inputmode="decimal" min="0" max="500" step="1" value="${w.min_margin_pct}" /><span class="input-suffix">%</span></div>
              <p class="hint">Kârın alış fiyatına oranı.</p>
            </div>
          </div>
          <div class="field">
            <label class="label" for="wf-int">Tarama aralığı</label>
            <div class="input-wrap"><input id="wf-int" class="input" name="interval_min" type="number" inputmode="numeric" min="${minInterval}" step="1" value="${w.interval_min}" /><span class="input-suffix">dk</span></div>
            <p class="hint">En az ${minInterval} dakika. Siteyi yormamak için çok sık taramayın.</p>
          </div>
          <div class="field">
            <label class="label" for="wf-inc">Başlıkta geçmesi gereken kelimeler <span class="opt">(isteğe bağlı)</span></label>
            <input id="wf-inc" class="input" name="include_words" type="text" value="${(w.include_words || []).join(', ')}" placeholder="ör. 128 GB, kutulu" autocomplete="off" />
            <p class="hint">Virgülle ayırın; en az biri geçen ilanlar alınır.</p>
          </div>
          <div class="field">
            <label class="label" for="wf-exc">Hariç tutulacak kelimeler <span class="opt">(isteğe bağlı)</span></label>
            <input id="wf-exc" class="input" name="exclude_words" type="text" value="${(w.exclude_words || []).join(', ')}" placeholder="ör. kılıf, kırık, parça" autocomplete="off" />
            <p class="hint">Virgülle ayırın; bu kelimeleri içeren ilanlar atlanır.</p>
          </div>
          <label class="switch">
            <input type="checkbox" name="active" ${w.active ? 'checked' : ''} />
            <span class="switch-track" aria-hidden="true"></span>
            <span class="switch-text"><span class="switch-label">Otomatik tara</span><span class="switch-hint">Kapalıyken yalnızca “Şimdi tara” ile taranır.</span></span>
          </label>
          <p class="field-error" data-form-error hidden></p>
        </form>`,
      footer: html`
        ${existing ? html`<button type="button" class="btn btn-ghost btn-danger spacer" data-del>${icon('trash', { size: 16 })}<span>Sil</span></button>` : ''}
        <button type="button" class="btn" data-close>Vazgeç</button>
        <button type="submit" form="watch-form" class="btn btn-primary" data-submit>${icon('check', { size: 18 })}<span>${existing ? 'Kaydet' : 'Takibi ekle'}</span></button>`,
    });
    const form = $('#watch-form', sheet.root);
    const err = $('[data-form-error]', sheet.root);
    form.addEventListener('change', (e) => {
      if (e.target.name === 'mode') {
        mode = e.target.value;
        $$('[data-mode]', form).forEach((x) => (x.hidden = x.dataset.mode !== mode));
        $(mode === 'url' ? '#wf-url' : '#wf-query', form).focus();
      }
    });
    form.addEventListener('focusout', (e) => {
      if (e.target.classList.contains('input-price')) {
        const v = parsePrice(e.target.value);
        if (v != null && !Number.isNaN(v)) e.target.value = priceInputValue(v);
      }
    });
    const fail = (msg, field) => {
      err.textContent = msg;
      err.hidden = false;
      if (field) {
        field.setAttribute('aria-invalid', 'true');
        field.focus();
      }
      return null;
    };
    const collect = () => {
      err.hidden = true;
      $$('[aria-invalid]', form).forEach((x) => x.removeAttribute('aria-invalid'));
      const fd = new FormData(form);
      const name = String(fd.get('name') || '').trim();
      if (!name) return fail('Liste adını girin.', $('#wf-name', form));
      const query = String(fd.get('query') || '').trim();
      const url = String(fd.get('search_url') || '').trim();
      if (mode === 'query' && !query) return fail('Arama kelimesini girin.', $('#wf-query', form));
      if (mode === 'url') {
        if (!url) return fail('Arama bağlantısını yapıştırın.', $('#wf-url', form));
        if (!safeUrl(url) || !/^https?:/i.test(url)) return fail('Geçerli bir bağlantı girin (https:// ile başlamalı).', $('#wf-url', form));
      }
      const num = (key, id, { allowEmpty = true, price = true } = {}) => {
        const raw = String(fd.get(key) || '').trim();
        if (!raw) return allowEmpty ? null : undefined;
        const v = price ? parsePrice(raw) : Number(raw.replace(',', '.'));
        if (!Number.isFinite(v) || v < 0) {
          fail('Sayısal bir değer girin.', $(id, form));
          return undefined;
        }
        return v;
      };
      const pmin = num('price_min', '#wf-pmin');
      if (pmin === undefined) return null;
      const pmax = num('price_max', '#wf-pmax');
      if (pmax === undefined) return null;
      if (pmin != null && pmax != null && pmin > pmax) return fail('En düşük fiyat en yüksek fiyattan büyük olamaz.', $('#wf-pmin', form));
      const profit = num('min_profit', '#wf-profit', { allowEmpty: false });
      if (profit === undefined) return fail('En az kârı girin.', $('#wf-profit', form));
      const margin = num('min_margin_pct', '#wf-margin', { allowEmpty: false, price: false });
      if (margin === undefined) return fail('En az marjı girin.', $('#wf-margin', form));
      const interval = num('interval_min', '#wf-int', { allowEmpty: false, price: false });
      if (interval === undefined) return fail('Tarama aralığını girin.', $('#wf-int', form));
      return {
        name,
        platform: fd.get('platform') || 'sahibinden',
        query: mode === 'query' ? query : '',
        search_url: mode === 'url' ? url : '',
        price_min: pmin,
        price_max: pmax,
        min_profit: profit,
        min_margin_pct: margin,
        interval_min: Math.max(minInterval, Math.round(interval)),
        include_words: splitWords(fd.get('include_words')),
        exclude_words: splitWords(fd.get('exclude_words')),
        active: fd.get('active') === 'on',
      };
    };
    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const data = collect();
      if (!data) return;
      const btn = $('[data-submit]', sheet.root);
      setBusy(btn, true, 'Kaydediliyor…');
      try {
        const saved = existing ? await api.put(`/api/watches/${existing.id}`, data) : await api.post('/api/watches', data);
        sheet.close('saved');
        toast.success(existing ? 'Takip listesi güncellendi.' : 'Takip listesi eklendi.', !existing && saved.active ? { title: 'İlk tarama birazdan başlayacak' } : {});
        await load();
        if (!existing && saved && saved.id) {
          const node = $(`[data-watch="${saved.id}"]`, $list);
          if (node) node.scrollIntoView({ block: 'center', behavior: 'smooth' });
        }
      } catch (ex) {
        setBusy(btn, false);
        fail(ex.message);
      }
    });
    const del = $('[data-del]', sheet.root);
    if (del) del.addEventListener('click', async () => {
      if (await removeWatch(existing)) sheet.close('deleted');
    });
    return sheet;
  }

  async function removeWatch(w) {
    const ok = await confirmDialog({
      title: 'Takip listesi silinsin mi?',
      message: `“${w.name}” silinecek ve artık taranmayacak. Bulunan fırsatlar listede kalır.`,
      confirmText: 'Sil',
      danger: true,
    });
    if (!ok) return false;
    try {
      await api.del(`/api/watches/${w.id}`);
      toast.success('Takip listesi silindi.');
      await load();
      return true;
    } catch (e) {
      showError(e);
      return false;
    }
  }

  // ---------------------------------------------------------------- olaylar
  root.addEventListener('click', async (e) => {
    if (e.target.closest('[data-new]')) {
      openForm();
      return;
    }
    if (e.target.closest('[data-action="retry"]')) {
      load();
      return;
    }
    const jobOpen = e.target.closest('[data-job-open]');
    if (jobOpen) {
      openJobsDrawer(jobOpen.dataset.jobOpen);
      return;
    }
    const cardEl = e.target.closest('[data-watch]');
    if (!cardEl || !watches) return;
    const w = watches.find((x) => x.id === Number(cardEl.dataset.watch));
    if (!w) return;
    if (e.target.closest('[data-edit]')) openForm(w);
    else if (e.target.closest('[data-delete]')) removeWatch(w);
    else {
      const scan = e.target.closest('[data-scan]');
      if (scan) {
        setBusy(scan, true, 'Başlatılıyor…');
        try {
          const job = await api.post(`/api/watches/${w.id}/scan`);
          trackJob(job);
          follow(w.id, job);
          rerenderCard(w.id);
          toast.info(`${platformName(w.platform)} araması açılıyor…`, { title: `${w.name}: tarama başladı` });
        } catch (err) {
          setBusy(scan, false);
          showError(err);
        }
      }
    }
  });

  root.addEventListener('change', async (e) => {
    const t = e.target;
    if (!t.matches('[data-active]')) return;
    const id = Number(t.closest('[data-watch]').dataset.watch);
    const w = watches.find((x) => x.id === id);
    t.disabled = true;
    try {
      const saved = await api.put(`/api/watches/${id}`, { active: t.checked });
      Object.assign(w, saved);
      toast.success(saved.active ? `“${w.name}” otomatik taranacak.` : `“${w.name}” otomatik taraması durduruldu.`);
    } catch (err) {
      t.checked = !t.checked;
      showError(err);
    } finally {
      rerenderCard(id);
    }
  });

  ctx.scope.cleanup(() => {
    for (const r of runners.values()) r.stop && r.stop();
    runners.clear();
  });

  await load();
  if (ctx.query.get('yeni')) {
    replaceQuery({});
    openForm();
  }
  ctx.scope.interval(load, 20000);
  return {};
}
