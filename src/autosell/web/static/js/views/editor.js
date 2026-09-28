// İlan düzenleyici: fotoğraflar, ürün analizi, platform metinleri, fiyat araştırması ve yayınlama.
import { api, upload, enc } from '../api.js';
import {
  html, $, $$, fmtPrice, fmtRel, timeAgo, parsePrice, priceInputValue, isNum, debounce, autosize,
  store, copyText, locative, safeUrl, platformName,
} from '../util.js';
import { icon } from '../icons.js';
import {
  toast, showError, confirmDialog, callout, errorState, emptyState, pubChip, pubInfo, scoreBadge,
  setBusy, withBusy, openLightbox, spinner,
} from '../ui.js';
import { navigate, replaceQuery } from '../router.js';
import { jobCard, trackJob, onJobsChange, isActive, friendlyError } from '../jobs.js';
import { researchResult } from '../research.js';
import { getStatus } from '../state.js';

const clone = (v) => JSON.parse(JSON.stringify(v));

export async function mount(root, ctx) {
  const id = ctx.params[0];
  let draft = null;
  let form = null;
  let base = '';
  let tab = null;
  let status = null;
  let generating = false;
  let saving = false;
  let research = null; // { result, job }
  let researchPlatform = null;
  const cards = new Map(); // iş id → kart
  const scores = {}; // platform → {score, notes}
  const catEditing = new Set();
  const activePublish = new Map(); // platform → iş
  let photoBusy = false;

  root.innerHTML = html`<div class="view-loading"><span class="spinner"></span><span class="sr-only">İlan yükleniyor…</span></div>`.s;

  // ---------------------------------------------------------------- durum
  const pickForm = (d) => ({
    notes: d.notes || '',
    price: d.price ?? null,
    priceRaw: priceInputValue(d.price),
    listings: Object.fromEntries(d.platforms.map((p) => {
      const l = d.listings[p] || {};
      return [p, {
        title: l.title || '',
        description: l.description || '',
        category_path: [...(l.category_path || [])],
        attributes: (l.attributes || []).map((a) => ({ name: a.name, value: a.value })),
        price: l.price ?? null,
        priceRaw: priceInputValue(l.price),
        override: l.price != null,
      }];
    })),
  });
  const snap = () => JSON.stringify({
    notes: form.notes,
    price: form.priceRaw.trim(),
    listings: Object.fromEntries(Object.entries(form.listings).map(([p, l]) => [p, {
      title: l.title, description: l.description, category_path: l.category_path, attributes: l.attributes,
      price: l.override ? l.priceRaw.trim() : '',
    }])),
  });
  const isDirty = () => !!form && snap() !== base;

  function updateDirty() {
    const dirty = isDirty();
    const bar = $('[data-savebar]', root);
    if (bar) bar.hidden = !dirty;
    document.body.classList.toggle('has-savebar', dirty);
  }
  ctx.scope.cleanup(() => document.body.classList.remove('has-savebar'));

  // ---------------------------------------------------------------- yükleme
  async function load() {
    try {
      const [d, s] = await Promise.all([api(`/api/drafts/${enc(id)}`, { signal: ctx.signal }), getStatus().catch(() => null)]);
      if (!ctx.alive()) return false;
      draft = d;
      status = s;
      return true;
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return false;
      if (e.status === 404) {
        root.innerHTML = html`<div class="card">${emptyState({
          icon: 'search',
          title: 'İlan bulunamadı',
          text: 'Bu ilan silinmiş olabilir.',
          action: html`<a class="btn btn-primary" href="#/ilanlar">İlanlarıma dön</a>`,
        })}</div>`.s;
      } else {
        root.innerHTML = html`<div class="card">${errorState(e)}</div>`.s;
        $('[data-action="retry"]', root).addEventListener('click', init);
      }
      return false;
    }
  }

  function resetForm() {
    form = pickForm(draft);
    base = snap();
    if (!tab || !draft.platforms.includes(tab)) tab = draft.platforms[0] || null;
    for (const p of draft.platforms) {
      const l = draft.listings[p];
      const cand = l && (l.title_candidates || []).find((c) => c.text === form.listings[p].title);
      if (cand) scores[p] = { score: cand.score, notes: cand.notes };
      else delete scores[p];
    }
  }

  // ---------------------------------------------------------------- iskelet
  function renderAll() {
    const gen = draft.generated;
    root.innerHTML = html`
      <div class="editor ${generating ? 'is-generating' : ''}">
        <header class="page-head editor-head">
          <div class="page-head-main">
            <a class="page-back desktop-only" href="#/ilanlar">${icon('chevronLeft', { size: 18 })}İlanlarım</a>
            <h1 class="page-title" data-title></h1>
            <div class="editor-meta" data-meta></div>
          </div>
          <div class="page-actions">
            <button type="button" class="btn" data-regen>${icon('sparkles', { size: 18 })}<span>${gen ? 'Yeniden oluştur' : 'Yapay zekâ ile oluştur'}</span></button>
            <button type="button" class="btn btn-danger btn-icon" data-delete aria-label="İlanı sil" title="İlanı sil">${icon('trash', { size: 18 })}</button>
          </div>
        </header>
        <div class="stack" data-alerts></div>
        <div class="job-stack" data-jobs aria-live="polite"></div>
        <div class="editor-grid">
          <div class="editor-main">
            <section class="card ed-card ed-platforms" aria-label="Platform metinleri" data-platforms></section>
          </div>
          <aside class="editor-aside">
            <section class="card ed-card ed-photos" aria-labelledby="ed-photos-t" data-photos></section>
            <section class="card ed-card ed-price" aria-labelledby="ed-price-t" data-price-card></section>
            <section class="card ed-card ed-product" aria-labelledby="ed-product-t" data-product></section>
          </aside>
        </div>
        <div class="savebar" data-savebar hidden role="region" aria-label="Kaydedilmemiş değişiklikler">
          <span class="savebar-text">${icon('pencil', { size: 18 })}<span>Kaydedilmemiş değişiklikler</span></span>
          <button type="button" class="btn btn-ghost" data-discard>Vazgeç</button>
          <button type="button" class="btn btn-primary" data-save>${icon('check', { size: 18 })}<span>Kaydet</span></button>
        </div>
      </div>`.s;
    renderHead();
    renderAlerts();
    renderPlatforms();
    renderPhotos();
    renderPrice();
    renderProduct();
    reattachCards();
    setGenerating(generating);
    updateDirty();
    ctx.setTitle(draft.display_title || 'İlan');
  }

  function renderHead() {
    $('[data-title]', root).textContent = draft.display_title || 'Adsız ilan';
    $('[data-meta]', root).innerHTML = html`
      <span class="chips">${draft.platforms.map((p) => pubChip(p, draft.publications[p]))}</span>
      <span class="muted small">${timeAgo(draft.updated_at, 'Güncellendi ')}</span>
      ${draft.ai_model ? html`<span class="muted small nowrap">${icon('bot', { size: 14 })} ${draft.ai_model}</span>` : ''}`.s;
  }

  function renderAlerts() {
    const out = [];
    if (draft.last_error) {
      out.push(callout({
        tone: 'warning',
        title: 'Yapay zekâ bu ilanı oluşturamadı',
        text: draft.last_error,
        action: html`<a class="btn btn-sm" href="#/ayarlar?b=ai">Ayarlar</a>`,
      }));
    }
    if (!draft.generated && !generating && !draft.last_error) {
      out.push(callout({
        tone: 'accent',
        icon: 'sparkles',
        title: 'Bu taslak henüz yapay zekâ ile oluşturulmadı',
        text: 'Başlık, açıklama, kategori ve özellikleri fotoğraflarınıza ve notlarınıza göre hazırlatın.',
        action: html`<button type="button" class="btn btn-sm btn-primary" data-regen>Oluştur</button>`,
      }));
    }
    if (status && !status.seller_ready) {
      out.push(callout({
        tone: 'warning',
        title: 'İl/ilçe girilmedi',
        text: 'Yayınlamadan önce Ayarlar › Satıcı Profili bölümünden konumunuzu girin.',
        action: html`<a class="btn btn-sm" href="#/ayarlar?b=seller">Konumu gir</a>`,
      }));
    }
    const box = $('[data-alerts]', root);
    box.innerHTML = html`${out}`.s;
    box.hidden = !out.length;
  }

  // ---------------------------------------------------------------- platform sekmeleri
  function renderPlatforms() {
    const box = $('[data-platforms]', root);
    if (!draft.platforms.length) {
      box.innerHTML = emptyState({ icon: 'store', title: 'Platform seçilmemiş', text: 'Bu taslak için yayın platformu yok.' }).s;
      return;
    }
    box.innerHTML = html`
      <div class="tabs" role="tablist" aria-label="Platformlar">
        ${draft.platforms.map((p) => html`
          <button type="button" class="tab" role="tab" id="tab-${p}" aria-controls="panel-${p}" aria-selected="${tab === p}" tabindex="${tab === p ? 0 : -1}" data-tab="${p}">
            <i class="pdot pdot-${p}" aria-hidden="true"></i>${(draft.rules[p] && draft.rules[p].name) || platformName(p)}
            <span class="tab-status" data-tab-status="${p}">${pubDot(p)}</span>
          </button>`)}
      </div>
      ${draft.platforms.map((p) => html`
        <div class="tabpanel" role="tabpanel" id="panel-${p}" aria-labelledby="tab-${p}" data-panel="${p}" ${tab === p ? '' : 'hidden'}></div>`)}
      <div class="gen-overlay" aria-hidden="true">
        <div class="gen-overlay-inner">${icon('sparkles', { size: 22 })}<span>Yapay zekâ ilanı hazırlıyor…</span></div>
      </div>`.s;
    for (const p of draft.platforms) renderPanel(p);
  }

  function pubDot(p) {
    const pub = draft.publications[p];
    if (!pub) return '';
    const info = pubInfo(pub.status);
    return html`<span class="sdot sdot-${info.tone}" title="${info.label}"></span>`;
  }

  function panelEl(p) {
    return $(`[data-panel="${p}"]`, root);
  }

  function renderPanel(p) {
    const el = panelEl(p);
    const l = form.listings[p];
    const rules = draft.rules[p] || { title_max: 60, description_max: 4000, name: platformName(p) };
    const name = rules.name || platformName(p);
    el.innerHTML = html`
      <div class="field">
        <div class="label-row">
          <label class="label" for="title-${p}">Başlık</label>
          <span class="counter" data-count="title"></span>
        </div>
        <div class="input-row">
          <input id="title-${p}" class="input input-title" type="text" value="${l.title}" data-field="title" autocomplete="off" spellcheck="true" />
          <button type="button" class="btn btn-icon" data-copy="title" aria-label="Başlığı kopyala" title="Kopyala">${icon('copy', { size: 18 })}</button>
        </div>
        <div class="title-score" data-score aria-live="polite"></div>
      </div>

      <div class="field">
        <span class="label">${icon('sparkles', { size: 15 })}Yapay zekâ başlık önerileri</span>
        <ul class="cands" data-cands></ul>
      </div>

      <div class="field">
        <div class="label-row">
          <label class="label" for="desc-${p}">Açıklama</label>
          <span class="row"><span class="counter" data-count="description"></span>
            <button type="button" class="btn btn-ghost btn-sm" data-copy="description">${icon('copy', { size: 15 })}<span>Kopyala</span></button></span>
        </div>
        <textarea id="desc-${p}" class="textarea desc-area" rows="10" data-field="description">${l.description}</textarea>
        ${rules.use_emoji ? '' : html`<p class="hint">${name} ilanlarında emoji kullanılmaz.</p>`}
      </div>

      <div class="field">
        <div class="label-row">
          <span class="label" id="cat-l-${p}">Kategori</span>
          <button type="button" class="btn btn-ghost btn-sm" data-cat-toggle aria-expanded="${catEditing.has(p)}">${icon(catEditing.has(p) ? 'check' : 'pencil', { size: 15 })}<span>${catEditing.has(p) ? 'Bitti' : 'Düzenle'}</span></button>
        </div>
        <div data-cat aria-labelledby="cat-l-${p}"></div>
      </div>

      <div class="field">
        <div class="label-row"><span class="label">Özellikler</span><span class="counter" data-attr-count></span></div>
        <div class="attrs" data-attrs></div>
        <div><button type="button" class="btn btn-sm" data-attr-add>${icon('plus', { size: 16 })}<span>Özellik ekle</span></button></div>
      </div>

      <div class="field">
        <label class="switch">
          <input type="checkbox" data-override ${l.override ? 'checked' : ''} />
          <span class="switch-track" aria-hidden="true"></span>
          <span class="switch-text"><span class="switch-label">${locative(name)} farklı fiyat kullan</span><span class="switch-hint">Kapalıyken genel fiyat (${form.price == null ? 'girilmedi' : fmtPrice(form.price)}) kullanılır.</span></span>
        </label>
        <div class="input-wrap override-wrap" ${l.override ? '' : 'hidden'}>
          <label class="sr-only" for="pprice-${p}">${name} fiyatı</label>
          <input id="pprice-${p}" class="input input-price" type="text" inputmode="numeric" autocomplete="off" placeholder="ör. 32.500" value="${l.priceRaw}" data-field="price" />
          <span class="input-suffix">TL</span>
        </div>
      </div>

      <div class="publish" data-publish></div>`.s;
    renderCounters(p);
    renderScore(p);
    renderCands(p);
    renderCat(p);
    renderAttrs(p);
    renderPublish(p);
    autosize($('.desc-area', el));
  }

  function renderCounters(p) {
    const el = panelEl(p);
    const l = form.listings[p];
    const rules = draft.rules[p] || {};
    const set = (key, n, max) => {
      const c = $(`[data-count="${key}"]`, el);
      if (!c) return;
      c.textContent = `${n}/${max}`;
      c.classList.toggle('is-over', n > max);
      c.classList.toggle('is-near', n <= max && n > max * 0.95);
      c.setAttribute('aria-label', `${n} karakter, sınır ${max}${n > max ? ', sınır aşıldı' : ''}`);
    };
    set('title', [...l.title].length, rules.title_max || 60);
    set('description', [...l.description].length, rules.description_max || 4000);
    const titleInput = $('[data-field="title"]', el);
    if (titleInput) titleInput.setAttribute('aria-invalid', String([...l.title].length > (rules.title_max || 60)));
  }

  function renderScore(p) {
    const el = panelEl(p);
    const box = $('[data-score]', el);
    if (!box) return;
    const s = scores[p];
    box.classList.toggle('is-stale', !!(s && s.stale));
    if (!s) {
      box.innerHTML = form.listings[p].title.trim()
        ? html`<span class="score-loading">${spinner(12)}<span>Başlık puanlanıyor…</span></span>`.s
        : html`<span class="muted small">Başlık girin; arama görünürlüğü puanı burada görünür.</span>`.s;
      return;
    }
    box.innerHTML = html`
      ${scoreBadge(s.score, { label: 'Başlık puanı' })}
      <ul class="score-notes">${(s.notes || []).map((n) => html`<li>${n}</li>`)}</ul>`.s;
  }

  const scoreLater = {};
  function queueScore(p) {
    if (scores[p]) scores[p].stale = true;
    renderScore(p);
    if (!scoreLater[p]) {
      scoreLater[p] = debounce(async () => {
        const title = form.listings[p].title;
        if (!title.trim()) {
          delete scores[p];
          renderScore(p);
          return;
        }
        try {
          const r = await api.post('/api/title-score', { platform: p, title, draft_id: id });
          if (!ctx.alive() || form.listings[p].title !== title) return;
          scores[p] = { score: r.score, notes: r.notes };
          renderScore(p);
          renderCands(p);
        } catch (e) {
          if (e.status !== 401) {
            const box = $('[data-score]', panelEl(p));
            if (box) box.innerHTML = html`<span class="muted small">Puan hesaplanamadı.</span>`.s;
          }
        }
      }, 450);
    }
    scoreLater[p]();
  }

  function renderCands(p) {
    const el = panelEl(p);
    const list = $('[data-cands]', el);
    if (!list) return;
    const l = draft.listings[p];
    const cands = [...((l && l.title_candidates) || [])].sort((a, b) => b.score - a.score);
    if (!cands.length) {
      list.innerHTML = html`<li class="muted small">Öneri yok. Yapay zekâ ile oluşturduğunuzda başlık önerileri burada listelenir.</li>`.s;
      return;
    }
    const current = form.listings[p].title;
    const max = (draft.rules[p] || {}).title_max || 60;
    list.innerHTML = html`${cands.map((c, i) => {
      const used = c.text === current;
      return html`
        <li>
          <button type="button" class="cand ${used ? 'is-used' : ''}" data-cand="${i}" aria-pressed="${used}" title="${(c.notes || []).join(' · ')}">
            ${scoreBadge(c.score, { label: 'Öneri puanı' })}
            <span class="cand-main">
              <span class="cand-text">${c.text}</span>
              <span class="cand-notes">${[...c.text].length}/${max}${c.notes && c.notes.length ? ` · ${c.notes.slice(0, 2).join(' · ')}` : ''}</span>
            </span>
            <span class="cand-use">${used ? html`${icon('check', { size: 15, strokeWidth: 2.4 })}<span>Kullanılıyor</span>` : 'Kullan'}</span>
          </button>
        </li>`;
    })}`.s;
    list.dataset.cands = JSON.stringify(cands.map((c) => c.text));
  }

  function renderCat(p) {
    const el = panelEl(p);
    const box = $('[data-cat]', el);
    const path = form.listings[p].category_path;
    if (catEditing.has(p)) {
      box.innerHTML = html`
        <ol class="cat-edit">
          ${path.map((seg, i) => html`
            <li class="cat-row">
              <span class="cat-level" aria-hidden="true">${i + 1}</span>
              <label class="sr-only" for="cat-${p}-${i}">${i + 1}. kategori seviyesi</label>
              <input id="cat-${p}-${i}" class="input" type="text" value="${seg}" data-cat-i="${i}" />
              <button type="button" class="btn btn-ghost btn-icon" data-cat-remove="${i}" aria-label="${i + 1}. seviyeyi kaldır">${icon('x', { size: 18 })}</button>
            </li>`)}
        </ol>
        <button type="button" class="btn btn-sm" data-cat-add>${icon('plus', { size: 16 })}<span>Alt kategori ekle</span></button>`.s;
      return;
    }
    box.innerHTML = path.filter((s) => s.trim()).length
      ? html`<ol class="crumbs">${path.filter((s) => s.trim()).map((seg, i, arr) => html`<li><span class="crumb ${i === arr.length - 1 ? 'is-last' : ''}">${seg}</span>${i < arr.length - 1 ? html`<span class="crumb-sep" aria-hidden="true">›</span>` : ''}</li>`)}</ol>`.s
      : html`<p class="muted small">Kategori belirlenmedi. Yayınlarken sitenin önerisi kullanılır; isterseniz <button type="button" class="link-btn" data-cat-toggle>elle girin</button>.</p>`.s;
  }

  function renderAttrs(p) {
    const el = panelEl(p);
    const box = $('[data-attrs]', el);
    const attrs = form.listings[p].attributes;
    $('[data-attr-count]', el).textContent = attrs.length ? `${attrs.length} özellik` : '';
    if (!attrs.length) {
      box.innerHTML = html`<p class="muted small">Henüz özellik yok. Marka, model, renk gibi bilgileri ekleyin; site formu doldurulurken kullanılır.</p>`.s;
      return;
    }
    box.innerHTML = html`
      <div class="attr-head" aria-hidden="true"><span>Özellik</span><span>Değer</span><span></span></div>
      ${attrs.map((a, i) => html`
        <div class="attr-row">
          <label class="sr-only" for="an-${p}-${i}">${i + 1}. özellik adı</label>
          <input id="an-${p}-${i}" class="input" type="text" value="${a.name}" placeholder="ör. Renk" data-attr-name="${i}" />
          <label class="sr-only" for="av-${p}-${i}">${i + 1}. özellik değeri</label>
          <input id="av-${p}-${i}" class="input" type="text" value="${a.value}" placeholder="ör. Mavi" data-attr-value="${i}" />
          <button type="button" class="btn btn-ghost btn-icon" data-attr-remove="${i}" aria-label="${a.name || `${i + 1}. özellik`} satırını kaldır">${icon('trash', { size: 17 })}</button>
        </div>`)}`.s;
  }

  function renderPublish(p) {
    const el = panelEl(p);
    const box = $('[data-publish]', el);
    if (!box) return;
    const pub = draft.publications[p];
    const name = (draft.rules[p] && draft.rules[p].name) || platformName(p);
    const running = activePublish.get(p);
    const auto = status && status.platforms && status.platforms[p] && status.platforms[p].auto_publish;
    const hintSeen = store.get('hint.publish', false);
    const url = pub && safeUrl(pub.url);
    box.innerHTML = html`
      <div class="publish-head">
        <h3 class="publish-title">${icon('upload', { size: 18 })}Yayın durumu</h3>
        ${pubChip(p, pub, { withName: false })}
      </div>
      ${pub ? html`
        <div class="publish-info">
          ${pub.message ? html`<p class="${pub.status === 'hata' ? 'text-danger' : 'muted-2'} small">${pub.status === 'hata' ? friendlyError(pub.message) : pub.message}</p>` : ''}
          <p class="muted small">${pub.listing_no ? html`İlan no: <strong class="num">${pub.listing_no}</strong> · ` : ''}${fmtRel(pub.updated_at)}</p>
          ${url ? html`<a class="btn btn-sm" href="${url}" target="_blank" rel="noopener">${icon('external', { size: 15 })}<span>İlanı sitede aç</span></a>` : ''}
        </div>` : html`<p class="muted small">Bu ilan henüz ${locative(name)} yayınlanmadı.</p>`}
      ${auto ? html`<p class="auto-warn">${icon('zap', { size: 15 })}<span>Otomatik yayın açık: son adım onay beklemeden tıklanır.</span></p>` : ''}
      <button type="button" class="btn btn-primary btn-block btn-publish" data-publish-btn="${p}" ${running ? 'disabled' : ''}>
        ${running ? html`${spinner(16)}<span>${running.status === 'waiting' ? 'Onayınız bekleniyor…' : 'Yayınlanıyor…'}</span>` : html`${icon('upload', { size: 18 })}<span>${pub && pub.status === 'yayinda' ? `${locative(name)} tekrar yayınla` : `${locative(name)} yayınla`}</span>`}
      </button>
      ${hintSeen ? html`<p class="hint center"><button type="button" class="link-btn" data-publish-help>Yayınlama nasıl çalışır?</button></p>` : publishHint()}`.s;
  }

  function publishHint() {
    return html`
      <div class="publish-hint" data-publish-hint>
        ${icon('info', { size: 18 })}
        <p>Yayınla'ya bastığınızda <strong>AutoSell'in çalıştığı bilgisayarda</strong> bir tarayıcı penceresi açılır ve ilan formu otomatik doldurulur. Varsayılan olarak son <strong>“Yayınla”</strong> adımından önce durur ve sizden onay ister; onayı buradan (telefondan da) verebilirsiniz.</p>
        <button type="button" class="btn btn-ghost btn-icon btn-sm" data-hint-close aria-label="Bilgiyi kapat">${icon('x', { size: 16 })}</button>
      </div>`;
  }

  // ---------------------------------------------------------------- fotoğraflar
  function renderPhotos() {
    const box = $('[data-photos]', root);
    const photos = draft.photos || [];
    const urls = draft.photo_urls || [];
    box.innerHTML = html`
      <header class="card-head">
        <h2 class="card-title" id="ed-photos-t">${icon('image', { size: 18 })}Fotoğraflar <span class="muted">(${photos.length})</span></h2>
        <label class="btn btn-sm head-actions ${photoBusy ? 'is-disabled' : ''}">
          <input type="file" accept="image/*" multiple class="sr-only" data-photo-add ${photoBusy ? 'disabled' : ''} />
          ${photoBusy ? spinner(14) : icon('plus', { size: 16 })}<span>${photoBusy ? 'Yükleniyor…' : 'Ekle'}</span>
        </label>
      </header>
      <div class="card-body">
        ${photos.length ? html`
          <ul class="photo-strip" data-photo-list>
            ${photos.map((name, i) => html`
              <li class="thumb" data-name="${name}" draggable="true">
                <button type="button" class="thumb-img" data-photo-view="${i}" aria-label="${i + 1}. fotoğrafı büyüt">
                  <img src="${urls[i]}" alt="" loading="lazy" data-fallback />
                </button>
                ${i === 0 ? html`<span class="thumb-badge">Kapak</span>` : ''}
                <div class="thumb-actions">
                  <button type="button" class="thumb-btn" data-photo-move="-1" ${i === 0 ? 'disabled' : ''} aria-label="${i + 1}. fotoğrafı sola taşı">${icon('chevronLeft', { size: 16 })}</button>
                  ${i !== 0 ? html`<button type="button" class="thumb-btn" data-photo-cover aria-label="${i + 1}. fotoğrafı kapak yap" title="Kapak yap">${icon('star', { size: 15 })}</button>` : ''}
                  <button type="button" class="thumb-btn" data-photo-move="1" ${i === photos.length - 1 ? 'disabled' : ''} aria-label="${i + 1}. fotoğrafı sağa taşı">${icon('chevronRight', { size: 16 })}</button>
                  <button type="button" class="thumb-btn is-danger" data-photo-delete aria-label="${i + 1}. fotoğrafı sil">${icon('trash', { size: 15 })}</button>
                </div>
              </li>`)}
          </ul>
          <p class="hint">İlk fotoğraf kapak olarak kullanılır. Sıralamak için okları kullanın${matchMedia('(pointer: fine)').matches ? ' ya da sürükleyin' : ''}.</p>` : html`
          <label class="dropzone is-compact">
            <input type="file" accept="image/*" multiple class="sr-only" data-photo-add />
            <span class="dz-icon">${icon('camera', { size: 24 })}</span>
            <span class="dz-title">Fotoğraf ekle</span>
            <span class="dz-sub">Fotoğraflı ilanlar çok daha hızlı satılır.</span>
          </label>`}
      </div>`.s;
  }

  async function savePhotoOrder(order, message) {
    const prev = draft.photos;
    photoBusy = true;
    try {
      const d = await api.put(`/api/drafts/${enc(id)}`, { photos: order });
      draft.photos = d.photos;
      draft.photo_urls = d.photo_urls;
      draft.updated_at = d.updated_at;
      if (message) toast.success(message);
    } catch (e) {
      draft.photos = prev;
      showError(e);
    } finally {
      photoBusy = false;
      renderPhotos();
      renderHead();
    }
  }

  async function addPhotos(fileList) {
    const list = [...fileList].filter((f) => !f.type || f.type.startsWith('image/') || /\.(heic|heif)$/i.test(f.name));
    const tooBig = list.filter((f) => f.size > 25 * 1024 * 1024);
    const ok = list.filter((f) => f.size <= 25 * 1024 * 1024);
    if (tooBig.length) toast.warning(`${tooBig.length} fotoğraf 25 MB sınırını aştığı için eklenmedi.`);
    if (!ok.length) return;
    const fd = new FormData();
    ok.forEach((f) => fd.append('photos', f, f.name));
    photoBusy = true;
    renderPhotos();
    try {
      const d = await upload(`/api/drafts/${enc(id)}/photos`, fd, {
        onProgress: (p) => {
          const lbl = $('[data-photos] .head-actions span:last-child', root);
          if (lbl) lbl.textContent = p < 1 ? `%${Math.round(p * 100)}` : 'İşleniyor…';
        },
      });
      draft.photos = d.photos;
      draft.photo_urls = d.photo_urls;
      draft.updated_at = d.updated_at;
      toast.success(`${ok.length} fotoğraf eklendi.`);
    } catch (e) {
      showError(e);
    } finally {
      photoBusy = false;
      renderPhotos();
      renderHead();
    }
  }

  // ---------------------------------------------------------------- fiyat ve araştırma
  function renderPrice() {
    const box = $('[data-price-card]', root);
    const plats = draft.platforms.length ? draft.platforms : ['sahibinden'];
    if (!researchPlatform || !plats.includes(researchPlatform)) researchPlatform = plats[0];
    box.innerHTML = html`
      <header class="card-head">
        <h2 class="card-title" id="ed-price-t">${icon('coins', { size: 18 })}Fiyat</h2>
      </header>
      <div class="card-body stack">
        <div class="field">
          <label class="label" for="ed-price">Satış fiyatı</label>
          <div class="input-wrap">
            <input id="ed-price" class="input input-price input-price-lg" type="text" inputmode="numeric" autocomplete="off" placeholder="ör. 32.500" value="${form.priceRaw}" data-general-price />
            <span class="input-suffix">TL</span>
          </div>
          <p class="hint">Tüm platformlarda kullanılır; platform sekmesinden ayrı fiyat da verebilirsiniz.</p>
        </div>
        <div class="research-box">
          <div class="research-cta">
            <div>
              <strong class="small">Piyasa fiyatını araştır</strong>
              <p class="hint">Sitedeki benzer ilanları tarayıp fiyat önerir.</p>
            </div>
          </div>
          <div class="research-actions">
            ${plats.length > 1 ? html`
              <div class="segmented" role="radiogroup" aria-label="Araştırılacak platform">
                ${plats.map((p) => html`<label><input type="radio" name="rp" value="${p}" ${researchPlatform === p ? 'checked' : ''} data-rp /><span class="seg"><i class="pdot pdot-${p}"></i>${platformName(p)}</span></label>`)}
              </div>` : ''}
            <button type="button" class="btn btn-soft" data-research>${icon('search', { size: 17 })}<span>Fiyat araştır</span></button>
          </div>
          <div class="research-job" data-research-job></div>
          <div data-research-result></div>
        </div>
      </div>`.s;
    renderResearchResult();
  }

  function renderResearchResult() {
    const box = $('[data-research-result]', root);
    if (!box) return;
    box.replaceChildren();
    if (!research || !research.result) return;
    const when = research.job && research.job.finished_at;
    const head = document.createElement('p');
    head.className = 'muted small research-when';
    head.innerHTML = html`${icon('history', { size: 14 })}<span>Son araştırma ${when ? fmtRel(when) : ''}</span>`.s;
    box.appendChild(head);
    box.appendChild(researchResult(research.result, {
      compact: true,
      showRisky: false,
      currentPrice: form.price,
      onUsePrice: (v) => {
        form.price = v;
        form.priceRaw = priceInputValue(v);
        const inp = $('[data-general-price]', root);
        if (inp) {
          inp.value = form.priceRaw;
          inp.removeAttribute('aria-invalid');
        }
        updateDirty();
        refreshOverrideHints();
        renderResearchResult();
        toast.success(`Fiyat ${fmtPrice(v)} olarak ayarlandı. Kaydetmeyi unutmayın.`);
      },
    }));
  }

  function refreshOverrideHints() {
    for (const p of draft.platforms) {
      const hint = $('[data-override] ~ .switch-text .switch-hint', panelEl(p));
      if (hint) hint.textContent = `Kapalıyken genel fiyat (${form.price == null ? 'girilmedi' : fmtPrice(form.price)}) kullanılır.`;
    }
  }

  // ---------------------------------------------------------------- ürün analizi ve notlar
  function renderProduct() {
    const box = $('[data-product]', root);
    const pr = draft.product || {};
    const hasInsight = draft.generated && (pr.name || pr.highlights.length || pr.defects.length || pr.included.length);
    const list = (title, items, cls = '', ic = 'dot') => (items && items.length ? html`
      <div class="insight">
        <h3 class="insight-title">${title}</h3>
        <ul class="insight-list ${cls}">${items.map((t) => html`<li>${icon(ic, { size: 15, strokeWidth: 2.2 })}<span>${t}</span></li>`)}</ul>
      </div>` : '');
    const added = new Set((form.notes || '').split('\n').map((l) => l.split(':')[0].trim().toLocaleLowerCase('tr')));
    box.innerHTML = html`
      <header class="card-head">
        <h2 class="card-title" id="ed-product-t">${icon('box', { size: 18 })}Ürün bilgisi</h2>
      </header>
      <div class="card-body stack">
        ${hasInsight ? html`
          <div class="product-id">
            <strong class="product-name">${pr.name || [pr.brand, pr.model].filter(Boolean).join(' ')}</strong>
            <div class="chips">
              ${pr.brand ? html`<span class="chip">Marka: ${pr.brand}</span>` : ''}
              ${pr.model ? html`<span class="chip">Model: ${pr.model}</span>` : ''}
              ${pr.condition ? html`<span class="chip chip-accent">Durum: ${pr.condition}</span>` : ''}
            </div>
          </div>
          ${(pr.warnings || []).length ? html`
            <div class="insight insight-warn" role="alert">
              <h3 class="insight-title">${icon('alert', { size: 15 })}Uyarılar</h3>
              <ul class="insight-list">${pr.warnings.map((w) => html`<li><span>${w}</span></li>`)}</ul>
            </div>` : ''}
          ${list('Öne çıkanlar', pr.highlights, 'is-good', 'check')}
          ${list('Kusurlar', pr.defects, 'is-bad', 'minus')}
          ${list('Kutu içeriği', pr.included, '', 'box')}
          ${(pr.keywords || []).length ? html`<div class="insight"><h3 class="insight-title">Anahtar kelimeler</h3><div class="chips">${pr.keywords.map((k) => html`<span class="chip chip-xs">${k}</span>`)}</div></div>` : ''}
        ` : ''}
        ${(pr.missing_info || []).length ? html`
          <div class="missing">
            <h3 class="insight-title">${icon('bulb', { size: 15 })}Eksik bilgiler</h3>
            <p class="hint">İlanı güçlendirmek için dokunun; notlara eklenir, değerini yazıp yeniden oluşturun.</p>
            <div class="chips">
              ${pr.missing_info.map((m) => {
                const done = added.has(m.toLocaleLowerCase('tr'));
                return html`<button type="button" class="chip chip-add ${done ? 'is-added' : ''}" data-missing="${m}" aria-pressed="${done}">${icon(done ? 'check' : 'plus', { size: 13 })}<span>${m}</span></button>`;
              })}
            </div>
          </div>` : ''}
        <div class="field">
          <label class="label" for="ed-notes">Notlarınız</label>
          <textarea id="ed-notes" class="textarea" rows="4" data-notes placeholder="Marka, model, kapasite, renk, kusurlar, kutu içeriği, garanti, satış nedeni…">${form.notes}</textarea>
          <p class="hint">Yapay zekâ ilanı bu notlara ve fotoğraflara göre yazar.</p>
        </div>
        <button type="button" class="btn btn-block" data-regen>${icon('sparkles', { size: 18 })}<span>${draft.generated ? 'Notlarla yeniden oluştur' : 'Yapay zekâ ile oluştur'}</span></button>
      </div>`.s;
    autosize($('[data-notes]', box));
  }

  // ---------------------------------------------------------------- işler
  function jobSlot(job) {
    return job.kind === 'research' ? $('[data-research-job]', root) : $('[data-jobs]', root);
  }

  function attachJob(job) {
    if (!job || cards.has(job.id)) return;
    const card = jobCard(job, {
      showLink: false,
      onUpdate: (j) => onJobUpdate(j),
      onDone: (j) => onJobDone(j),
      onDismiss: () => cards.delete(job.id),
    });
    cards.set(job.id, card);
    const slot = jobSlot(job);
    if (slot) slot.prepend(card.el);
    onJobUpdate(job);
  }

  function reattachCards() {
    for (const card of cards.values()) {
      const slot = jobSlot(card.job);
      if (slot && !slot.contains(card.el)) slot.prepend(card.el);
    }
  }

  function onJobUpdate(j) {
    if (j.kind === 'generate') setGenerating(isActive(j));
    if (j.kind === 'publish' && j.platform) {
      const was = activePublish.get(j.platform);
      if (isActive(j)) activePublish.set(j.platform, j);
      else activePublish.delete(j.platform);
      if (!was || !isActive(j) || was.status !== j.status) {
        if (draft && panelEl(j.platform)) renderPublish(j.platform);
      }
    }
    if (j.kind === 'research') {
      const btn = $('[data-research]', root);
      if (btn) {
        if (isActive(j)) setBusy(btn, true, 'Araştırılıyor…');
        else setBusy(btn, false);
      }
    }
  }

  async function onJobDone(j) {
    if (!ctx.alive()) return;
    if (j.kind === 'generate') {
      setGenerating(false);
      const ok = await load();
      if (!ok) return;
      resetForm();
      renderAll();
      if (j.status === 'done') toast.success('İlan metinleri hazır. Kontrol edip yayınlayabilirsiniz.');
    } else if (j.kind === 'publish') {
      try {
        const d = await api(`/api/drafts/${enc(id)}`);
        if (!ctx.alive()) return;
        draft.publications = d.publications;
        draft.updated_at = d.updated_at;
        renderHead();
        for (const p of draft.platforms) {
          renderPublish(p);
          const st = $(`[data-tab-status="${p}"]`, root);
          if (st) st.innerHTML = pubDot(p).s || '';
        }
      } catch {
        /* yok say */
      }
    } else if (j.kind === 'research') {
      if (j.status === 'done' && j.result) {
        research = { result: j.result, job: j };
        renderResearchResult();
      }
    }
  }

  function setGenerating(on) {
    generating = on;
    const ed = $('.editor', root);
    if (!ed) return;
    ed.classList.toggle('is-generating', on);
    for (const sel of ['[data-platforms]', '[data-product]', '[data-price-card]']) {
      const el = $(sel, root);
      if (el) {
        if (on) el.setAttribute('inert', '');
        else el.removeAttribute('inert');
      }
    }
    $$('[data-regen]', root).forEach((b) => (b.disabled = on));
  }

  // ---------------------------------------------------------------- kaydetme
  function validate() {
    if (form.priceRaw.trim() && Number.isNaN(parsePrice(form.priceRaw))) {
      const inp = $('[data-general-price]', root);
      inp.setAttribute('aria-invalid', 'true');
      inp.focus();
      toast.error('Fiyat sayı olmalı (ör. 32.500).');
      return false;
    }
    for (const p of draft.platforms) {
      const l = form.listings[p];
      if (l.override && l.priceRaw.trim() && Number.isNaN(parsePrice(l.priceRaw))) {
        selectTab(p);
        const inp = $('[data-field="price"]', panelEl(p));
        inp.setAttribute('aria-invalid', 'true');
        inp.focus();
        toast.error(`${platformName(p)} fiyatı sayı olmalı.`);
        return false;
      }
    }
    return true;
  }

  function payload() {
    const price = form.priceRaw.trim() ? parsePrice(form.priceRaw) : null;
    return {
      notes: form.notes,
      price,
      listings: Object.fromEntries(draft.platforms.map((p) => {
        const l = form.listings[p];
        return [p, {
          title: l.title.trim(),
          description: l.description,
          category_path: l.category_path.map((s) => s.trim()).filter(Boolean),
          attributes: l.attributes.map((a) => ({ name: a.name.trim(), value: a.value.trim() })).filter((a) => a.name && a.value),
          price: l.override && l.priceRaw.trim() ? parsePrice(l.priceRaw) : null,
        }];
      })),
    };
  }

  async function save({ quiet = false } = {}) {
    if (!form || saving) return false;
    if (!isDirty()) return true;
    if (!validate()) return false;
    saving = true;
    const btn = $('[data-save]', root);
    setBusy(btn, true, 'Kaydediliyor…');
    try {
      const sentSnap = snap();
      const d = await api.put(`/api/drafts/${enc(id)}`, payload());
      if (!ctx.alive()) return true;
      const keepTitles = Object.fromEntries(draft.platforms.map((p) => [p, draft.listings[p]]));
      draft = { ...d, listings: Object.fromEntries(Object.entries(d.listings).map(([p, l]) => [p, { ...l, title_candidates: l.title_candidates || (keepTitles[p] && keepTitles[p].title_candidates) || [] }])) };
      form.price = d.price;
      base = sentSnap;
      updateDirty();
      renderHead();
      ctx.setTitle(draft.display_title || 'İlan');
      if (!quiet) toast.success('Değişiklikler kaydedildi.');
      return true;
    } catch (e) {
      showError(e);
      return false;
    } finally {
      saving = false;
      if (btn && btn.isConnected) setBusy(btn, false);
    }
  }

  function discard() {
    resetForm();
    renderPlatforms();
    renderPrice();
    renderProduct();
    reattachCards();
    updateDirty();
    toast.info('Değişiklikler geri alındı.');
  }

  // ---------------------------------------------------------------- eylemler
  function selectTab(p, focus = false) {
    tab = p;
    for (const t of $$('[data-tab]', root)) {
      const on = t.dataset.tab === p;
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
      if (on && focus) t.focus();
    }
    for (const panel of $$('[data-panel]', root)) {
      panel.hidden = panel.dataset.panel !== p;
      if (!panel.hidden) autosize($('.desc-area', panel));
    }
  }

  async function regenerate() {
    if (generating) return;
    if (draft.generated) {
      const ok = await confirmDialog({
        title: 'İlan yeniden oluşturulsun mu?',
        message: 'Yapay zekâ başlık, açıklama, kategori ve özellikleri notlarınıza ve fotoğraflara göre yeniden yazacak. Metinlerde elle yaptığınız değişikliklerin üzerine yazılır.',
        confirmText: 'Yeniden oluştur',
        icon: 'sparkles',
      });
      if (!ok) return;
    }
    if (isDirty()) {
      const saved = await save({ quiet: true });
      if (!saved) return;
    }
    try {
      const job = await api.post(`/api/drafts/${enc(id)}/generate`);
      trackJob(job);
      setGenerating(true);
      attachJob(job);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      showError(e);
    }
  }

  async function publish(p, btn) {
    const name = (draft.rules[p] && draft.rules[p].name) || platformName(p);
    if (!validate()) return;
    const l = form.listings[p];
    const max = (draft.rules[p] || {}).title_max || 60;
    if (!l.title.trim()) {
      selectTab(p);
      $('[data-field="title"]', panelEl(p)).focus();
      toast.error('Önce bir başlık girin.');
      return;
    }
    if ([...l.title].length > max) {
      selectTab(p);
      $('[data-field="title"]', panelEl(p)).focus();
      toast.error(`Başlık ${name} sınırını (${max} karakter) aşıyor.`);
      return;
    }
    const price = l.override && l.priceRaw.trim() ? parsePrice(l.priceRaw) : form.priceRaw.trim() ? parsePrice(form.priceRaw) : null;
    if (price == null) {
      const inp = $('[data-general-price]', root);
      inp.focus();
      inp.setAttribute('aria-invalid', 'true');
      toast.error('Yayınlamadan önce bir satış fiyatı girin.');
      return;
    }
    if (status && !status.seller_ready) {
      const ok = await confirmDialog({
        title: 'Konum girilmemiş',
        message: 'Satıcı profilinizde il/ilçe yok; site formu konum isteyebilir ve yayın yarıda kalabilir. Yine de devam edilsin mi?',
        confirmText: 'Devam et',
        icon: 'alert',
      });
      if (!ok) return;
    }
    const pub = draft.publications[p];
    if (pub && pub.status === 'yayinda') {
      const ok = await confirmDialog({
        title: 'İlan zaten yayında',
        message: `Bu ilan ${locative(name)} zaten yayında. Tekrar yayınlamak sitede ikinci bir ilan oluşturabilir. Devam edilsin mi?`,
        confirmText: 'Yine de yayınla',
        danger: true,
      });
      if (!ok) return;
    }
    if (isDirty()) {
      const saved = await save({ quiet: true });
      if (!saved) return;
      toast.info('Değişiklikler kaydedildi.');
    }
    await withBusy(btn, 'Başlatılıyor…', async () => {
      try {
        const job = await api.post(`/api/drafts/${enc(id)}/publish`, { platform: p });
        trackJob(job);
        activePublish.set(p, job);
        attachJob(job);
        draft.publications[p] = { ...(draft.publications[p] || {}), status: 'calisiyor', updated_at: new Date().toISOString(), message: '' };
        renderHead();
        toast.info(`${name} tarayıcısı açılıyor. Form doldurulunca onayınız istenecek.`, { title: 'Yayınlama başladı' });
      } catch (e) {
        showError(e);
      }
    });
    renderPublish(p);
  }

  async function startResearch(btn) {
    try {
      setBusy(btn, true, 'Başlatılıyor…');
      const job = await api.post(`/api/drafts/${enc(id)}/research`, { platform: researchPlatform });
      trackJob(job);
      attachJob(job);
    } catch (e) {
      setBusy(btn, false);
      showError(e);
    }
  }

  async function deleteDraft() {
    const ok = await confirmDialog({
      title: 'İlan silinsin mi?',
      message: 'Taslak, fotoğrafları ve yayın kayıtları bu bilgisayardan kalıcı olarak silinir. Sitelerde yayındaki ilanlar bundan etkilenmez.',
      confirmText: 'Kalıcı olarak sil',
      danger: true,
    });
    if (!ok) return;
    try {
      await api.del(`/api/drafts/${enc(id)}`);
      toast.success('İlan silindi.');
      form = null;
      navigate('#/ilanlar', { force: true });
    } catch (e) {
      showError(e);
    }
  }

  // ---------------------------------------------------------------- olaylar
  root.addEventListener('input', (e) => {
    if (!form) return;
    const t = e.target;
    const panel = t.closest('[data-panel]');
    if (panel) {
      const p = panel.dataset.panel;
      const l = form.listings[p];
      if (t.dataset.field === 'title') {
        l.title = t.value;
        renderCounters(p);
        queueScore(p);
        renderCandsUsed(p);
      } else if (t.dataset.field === 'description') {
        l.description = t.value;
        autosize(t);
        renderCounters(p);
      } else if (t.dataset.field === 'price') {
        l.priceRaw = t.value;
        t.removeAttribute('aria-invalid');
      } else if (t.dataset.catI !== undefined) {
        l.category_path[Number(t.dataset.catI)] = t.value;
      } else if (t.dataset.attrName !== undefined) {
        l.attributes[Number(t.dataset.attrName)].name = t.value;
      } else if (t.dataset.attrValue !== undefined) {
        l.attributes[Number(t.dataset.attrValue)].value = t.value;
      }
      updateDirty();
      return;
    }
    if (t.matches('[data-general-price]')) {
      form.priceRaw = t.value;
      const v = parsePrice(t.value);
      form.price = v == null || Number.isNaN(v) ? null : v;
      t.removeAttribute('aria-invalid');
      refreshOverrideHints();
      updateDirty();
    } else if (t.matches('[data-notes]')) {
      form.notes = t.value;
      autosize(t);
      updateDirty();
    }
  });

  root.addEventListener('change', (e) => {
    const t = e.target;
    if (t.matches('[data-override]')) {
      const p = t.closest('[data-panel]').dataset.panel;
      form.listings[p].override = t.checked;
      const wrap = $('.override-wrap', panelEl(p));
      wrap.hidden = !t.checked;
      if (t.checked) $('input', wrap).focus();
      updateDirty();
    } else if (t.matches('[data-rp]')) {
      researchPlatform = t.value;
    } else if (t.matches('[data-photo-add]')) {
      if (t.files && t.files.length) addPhotos(t.files);
      t.value = '';
    }
  });

  root.addEventListener('focusout', (e) => {
    const t = e.target;
    if (t.matches('[data-general-price], .input-price')) {
      const v = parsePrice(t.value);
      if (v != null && !Number.isNaN(v)) {
        t.value = priceInputValue(v);
        if (t.matches('[data-general-price]')) form.priceRaw = t.value;
        else {
          const p = t.closest('[data-panel]');
          if (p) form.listings[p.dataset.panel].priceRaw = t.value;
        }
        updateDirty();
      }
    }
  });

  function renderCandsUsed(p) {
    const cur = form.listings[p].title;
    for (const b of $$('[data-cand]', panelEl(p))) {
      const text = $('.cand-text', b).textContent;
      const used = text === cur;
      b.classList.toggle('is-used', used);
      b.setAttribute('aria-pressed', String(used));
      $('.cand-use', b).innerHTML = used ? html`${icon('check', { size: 15, strokeWidth: 2.4 })}<span>Kullanılıyor</span>`.s : 'Kullan';
    }
  }

  root.addEventListener('click', async (e) => {
    const t = e.target;
    if (!form) return;
    const tabBtn = t.closest('[data-tab]');
    if (tabBtn) {
      selectTab(tabBtn.dataset.tab);
      return;
    }
    const panel = t.closest('[data-panel]');
    const p = panel && panel.dataset.panel;
    const cand = t.closest('[data-cand]');
    if (cand && p) {
      const text = $('.cand-text', cand).textContent;
      form.listings[p].title = text;
      const inp = $('[data-field="title"]', panel);
      inp.value = text;
      const c = (draft.listings[p].title_candidates || []).find((x) => x.text === text);
      if (c) scores[p] = { score: c.score, notes: c.notes };
      renderCounters(p);
      renderScore(p);
      renderCandsUsed(p);
      updateDirty();
      if (!c) queueScore(p);
      return;
    }
    const copy = t.closest('[data-copy]');
    if (copy && p) {
      const text = form.listings[p][copy.dataset.copy] || '';
      const ok = await copyText(text);
      if (ok) toast.success(copy.dataset.copy === 'title' ? 'Başlık kopyalandı.' : 'Açıklama kopyalandı.');
      else toast.error('Kopyalanamadı; metni elle seçip kopyalayın.');
      return;
    }
    if (t.closest('[data-cat-toggle]') && p) {
      if (catEditing.has(p)) {
        catEditing.delete(p);
        form.listings[p].category_path = form.listings[p].category_path.filter((s) => s.trim());
      } else {
        catEditing.add(p);
        if (!form.listings[p].category_path.length) form.listings[p].category_path.push('');
      }
      const btn = $('[data-cat-toggle].btn', panel);
      if (btn) {
        btn.setAttribute('aria-expanded', String(catEditing.has(p)));
        btn.innerHTML = html`${icon(catEditing.has(p) ? 'check' : 'pencil', { size: 15 })}<span>${catEditing.has(p) ? 'Bitti' : 'Düzenle'}</span>`.s;
      }
      renderCat(p);
      if (catEditing.has(p)) {
        const inputs = $$('[data-cat-i]', panel);
        if (inputs.length) inputs[inputs.length - 1].focus();
      }
      updateDirty();
      return;
    }
    const catRemove = t.closest('[data-cat-remove]');
    if (catRemove && p) {
      form.listings[p].category_path.splice(Number(catRemove.dataset.catRemove), 1);
      renderCat(p);
      updateDirty();
      return;
    }
    if (t.closest('[data-cat-add]') && p) {
      form.listings[p].category_path.push('');
      renderCat(p);
      const inputs = $$('[data-cat-i]', panel);
      inputs[inputs.length - 1].focus();
      updateDirty();
      return;
    }
    if (t.closest('[data-attr-add]') && p) {
      form.listings[p].attributes.push({ name: '', value: '' });
      renderAttrs(p);
      const names = $$('[data-attr-name]', panel);
      names[names.length - 1].focus();
      updateDirty();
      return;
    }
    const attrRemove = t.closest('[data-attr-remove]');
    if (attrRemove && p) {
      const i = Number(attrRemove.dataset.attrRemove);
      form.listings[p].attributes.splice(i, 1);
      renderAttrs(p);
      const next = $$('[data-attr-remove]', panel)[Math.min(i, form.listings[p].attributes.length - 1)];
      if (next) next.focus();
      else $('[data-attr-add]', panel).focus();
      updateDirty();
      return;
    }
    const pubBtn = t.closest('[data-publish-btn]');
    if (pubBtn) {
      publish(pubBtn.dataset.publishBtn, pubBtn);
      return;
    }
    if (t.closest('[data-hint-close]')) {
      store.set('hint.publish', true);
      for (const x of draft.platforms) renderPublish(x);
      return;
    }
    if (t.closest('[data-publish-help]')) {
      store.set('hint.publish', false);
      for (const x of draft.platforms) renderPublish(x);
      return;
    }
    if (t.closest('[data-regen]')) {
      regenerate();
      return;
    }
    if (t.closest('[data-delete]')) {
      deleteDraft();
      return;
    }
    if (t.closest('[data-save]')) {
      save();
      return;
    }
    if (t.closest('[data-discard]')) {
      discard();
      return;
    }
    const researchBtn = t.closest('[data-research]');
    if (researchBtn) {
      startResearch(researchBtn);
      return;
    }
    const missing = t.closest('[data-missing]');
    if (missing) {
      const label = missing.dataset.missing;
      const ta = $('[data-notes]', root);
      const lines = form.notes.split('\n');
      const exists = lines.some((l) => l.split(':')[0].trim().toLocaleLowerCase('tr') === label.toLocaleLowerCase('tr'));
      if (!exists) {
        const v = form.notes.replace(/\s+$/, '');
        form.notes = `${v}${v ? '\n' : ''}${label}: `;
        ta.value = form.notes;
        autosize(ta);
        missing.classList.add('is-added');
        missing.setAttribute('aria-pressed', 'true');
        missing.innerHTML = html`${icon('check', { size: 13 })}<span>${label}</span>`.s;
        updateDirty();
      }
      ta.focus();
      const pos = exists ? ta.value.indexOf(`${label}:`) + label.length + 2 : ta.value.length;
      ta.setSelectionRange(pos, pos);
      ta.scrollIntoView({ block: 'center', behavior: 'smooth' });
      return;
    }
    // fotoğraflar
    const thumb = t.closest('[data-photo-list] .thumb');
    if (thumb && !photoBusy) {
      const name = thumb.dataset.name;
      const idx = draft.photos.indexOf(name);
      const mv = t.closest('[data-photo-move]');
      if (mv) {
        const to = idx + Number(mv.dataset.photoMove);
        if (to < 0 || to >= draft.photos.length) return;
        const order = [...draft.photos];
        order.splice(idx, 1);
        order.splice(to, 0, name);
        await savePhotoOrder(order);
        const again = $(`.thumb[data-name="${CSS.escape(name)}"] [data-photo-move="${mv.dataset.photoMove}"]`, root);
        if (again && !again.disabled) again.focus();
        return;
      }
      if (t.closest('[data-photo-cover]')) {
        const order = [name, ...draft.photos.filter((x) => x !== name)];
        await savePhotoOrder(order, 'Kapak fotoğrafı değiştirildi.');
        return;
      }
      if (t.closest('[data-photo-delete]')) {
        const ok = await confirmDialog({ title: 'Fotoğraf silinsin mi?', message: 'Bu fotoğraf taslaktan kalıcı olarak silinir.', confirmText: 'Sil', danger: true });
        if (!ok) return;
        photoBusy = true;
        try {
          const d = await api.del(`/api/drafts/${enc(id)}/photos/${enc(name)}`);
          draft.photos = d.photos;
          draft.photo_urls = d.photo_urls;
          toast.success('Fotoğraf silindi.');
        } catch (err) {
          showError(err);
        } finally {
          photoBusy = false;
          renderPhotos();
        }
        return;
      }
      if (t.closest('[data-photo-view]')) openLightbox(draft.photo_urls, idx, { alt: draft.display_title });
    }
  });

  // klavye: sekmeler arasında ok tuşlarıyla gezinme, Ctrl+S ile kaydetme
  root.addEventListener('keydown', (e) => {
    const tabBtn = e.target.closest('[data-tab]');
    if (tabBtn && (e.key === 'ArrowRight' || e.key === 'ArrowLeft')) {
      const list = draft.platforms;
      const i = list.indexOf(tabBtn.dataset.tab);
      const next = list[(i + (e.key === 'ArrowRight' ? 1 : -1) + list.length) % list.length];
      selectTab(next, true);
      e.preventDefault();
    }
    if (e.target.matches('[data-attr-value]') && e.key === 'Enter') {
      e.preventDefault();
      $('[data-attr-add]', e.target.closest('[data-panel]')).click();
    }
    if (e.target.matches('[data-cat-i]') && e.key === 'Enter') {
      e.preventDefault();
      $('[data-cat-add]', e.target.closest('[data-panel]')).click();
    }
  });
  ctx.scope.on(document, 'keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
      e.preventDefault();
      if (isDirty()) save();
    }
  });

  // masaüstü: fotoğrafları sürükleyerek sıralama
  let dragName = null;
  root.addEventListener('dragstart', (e) => {
    const li = e.target.closest('[data-photo-list] .thumb');
    if (!li || photoBusy) return;
    dragName = li.dataset.name;
    li.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragName);
  });
  root.addEventListener('dragend', () => {
    dragName = null;
    $$('[data-photo-list] .thumb', root).forEach((x) => x.classList.remove('is-dragging', 'is-drop'));
  });
  root.addEventListener('dragover', (e) => {
    const li = e.target.closest('[data-photo-list] .thumb');
    if (dragName && li) {
      e.preventDefault();
      $$('[data-photo-list] .thumb', root).forEach((x) => x.classList.toggle('is-drop', x === li && x.dataset.name !== dragName));
    } else if (!dragName && e.dataTransfer && [...e.dataTransfer.types].includes('Files') && e.target.closest('[data-photos]')) {
      e.preventDefault();
    }
  });
  root.addEventListener('drop', (e) => {
    const li = e.target.closest('[data-photo-list] .thumb');
    if (dragName && li) {
      e.preventDefault();
      if (li.dataset.name === dragName) return;
      const order = draft.photos.filter((x) => x !== dragName);
      order.splice(order.indexOf(li.dataset.name) + (draft.photos.indexOf(dragName) < draft.photos.indexOf(li.dataset.name) ? 1 : 0), 0, dragName);
      savePhotoOrder(order);
    } else if (!dragName && e.dataTransfer && e.dataTransfer.files.length && e.target.closest('[data-photos]')) {
      e.preventDefault();
      addPhotos(e.dataTransfer.files);
    }
  });

  // ---------------------------------------------------------------- başlangıç
  async function init() {
    const ok = await load();
    if (!ok) return;
    resetForm();
    renderAll();
    for (const p of draft.platforms) if (!scores[p] && form.listings[p].title.trim()) queueScore(p);

    // bu ilanın işleri: adres çubuğundaki iş, aktif işler ve son fiyat araştırması
    const qJob = ctx.query.get('is');
    if (qJob) {
      try {
        const j = await api(`/api/jobs/${enc(qJob)}`);
        if (ctx.alive() && j.draft_id === id && (isActive(j) || Date.now() - new Date(j.finished_at || j.created_at).getTime() < 5 * 60000)) attachJob(j);
      } catch {
        /* iş geçmişten silinmiş olabilir */
      }
      replaceQuery({});
    }
    try {
      const jobs = await api('/api/jobs?limit=60');
      if (!ctx.alive()) return;
      jobs.filter((j) => j.draft_id === id && isActive(j)).forEach(attachJob);
      const lastResearch = jobs.find((j) => j.draft_id === id && j.kind === 'research' && j.status === 'done' && j.result);
      if (lastResearch && !research) {
        research = { result: lastResearch.result, job: lastResearch };
        renderResearchResult();
      }
    } catch {
      /* yok say */
    }
    ctx.scope.cleanup(onJobsChange((jobs) => {
      jobs.filter((j) => j.draft_id === id).forEach((j) => {
        if (!cards.has(j.id)) attachJob(j);
      });
    }));
  }

  ctx.scope.cleanup(() => {
    for (const c of cards.values()) c.stop();
    Object.values(scoreLater).forEach((d) => d.cancel && d.cancel());
  });

  await init();

  return {
    isDirty,
    save: () => save(),
    leaveMessage: 'Bu ilanda kaydetmediğiniz değişiklikler var. Kaydetmeden çıkarsanız kaybolacaklar.',
  };
}
