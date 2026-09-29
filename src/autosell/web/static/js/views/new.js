// Yeni ilan: fotoğraflar + notlar + fiyat + platformlar → yapay zekâ ile taslak oluşturma.
import { upload, enc } from '../api.js';
import { html, $, $$, parsePrice, priceInputValue, uid, autosize, store, platformName } from '../util.js';
import { icon } from '../icons.js';
import { toast, callout, openLightbox } from '../ui.js';
import { navigate } from '../router.js';
import { trackJob } from '../jobs.js';
import { getStatus } from '../state.js';

const MAX_BYTES = 25 * 1024 * 1024;
const NOTE_HINTS = [
  { label: 'Marka / model', line: 'Marka ve model: ' },
  { label: 'Kapasite', line: 'Kapasite / hafıza: ' },
  { label: 'Renk', line: 'Renk: ' },
  { label: 'Kusurlar', line: 'Kusurlar (çizik, kırık vb.): ' },
  { label: 'Kutu içeriği', line: 'Kutu içeriği: ' },
  { label: 'Garanti', line: 'Garanti durumu: ' },
  { label: 'Fatura', line: 'Fatura: ' },
  { label: 'Satış nedeni', line: 'Satış nedeni: ' },
];
const PLACEHOLDER = `Örnek:
iPhone 13, 128 GB, mavi. Pil sağlığı %89.
Kutusu ve faturası var, garantisi Mart 2026'ya kadar.
Kasada ufak bir çizik var, ekranı temiz.
Yeni telefon aldığım için satıyorum.`;

export async function mount(root, ctx) {
  const files = []; // { id, file, url }
  let busy = false;
  const draftNotes = store.get('new.notes', '');
  const draftPrice = store.get('new.price', '');
  let status = null;

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">Yeni İlan</h1>
        <p class="page-sub">Fotoğrafları ve birkaç notu ekleyin; başlığı, açıklamayı, kategoriyi ve özellikleri yapay zekâ hazırlasın.</p>
      </div>
    </header>
    <div data-ai-note></div>
    <form class="new-grid" novalidate>
      <section class="card new-photos" aria-labelledby="np-title">
        <header class="card-head">
          <h2 class="card-title" id="np-title">${icon('image', { size: 18 })}Fotoğraflar <span class="muted" data-count></span></h2>
          <span class="head-actions hint">İlk fotoğraf kapak olur</span>
        </header>
        <div class="card-body">
          <label class="dropzone" data-dropzone>
            <input type="file" accept="image/*" multiple class="sr-only" data-file />
            <span class="dz-icon">${icon('camera', { size: 28 })}</span>
            <span class="dz-title"><span class="desktop-only">Fotoğrafları sürükleyip bırakın</span><span class="mobile-only">Fotoğraf ekle</span></span>
            <span class="dz-sub"><span class="desktop-only">ya da seçmek için tıklayın · yapıştırmak için Ctrl+V</span><span class="mobile-only">Kameradan çekin ya da galeriden seçin</span></span>
            <span class="dz-types">JPG, PNG, HEIC · fotoğraf başına en fazla 25 MB</span>
          </label>
          <ul class="thumbs" data-thumbs aria-label="Seçilen fotoğraflar"></ul>
        </div>
      </section>

      <div class="new-side">
        <section class="card" aria-labelledby="nn-title">
          <header class="card-head">
            <h2 class="card-title" id="nn-title">${icon('pencil', { size: 18 })}Ürün notları</h2>
          </header>
          <div class="card-body">
            <div class="field">
              <label class="label" for="new-notes">Ürünü kısaca anlatın <span class="opt">(önerilir)</span></label>
              <textarea id="new-notes" class="textarea" rows="6" placeholder="${PLACEHOLDER}" data-notes>${draftNotes}</textarea>
              <p class="hint">Marka, model, kapasite, renk, kusurlar, kutu içeriği, garanti, satış nedeni… Ne kadar bilgi, o kadar iyi ilan.</p>
              <div class="chips note-hints" aria-label="Hızlı ekle">
                ${NOTE_HINTS.map((h) => html`<button type="button" class="chip chip-add" data-hint="${h.line}">${icon('plus', { size: 13 })}<span>${h.label}</span></button>`)}
              </div>
            </div>
          </div>
        </section>

        <section class="card" aria-labelledby="npr-title">
          <header class="card-head">
            <h2 class="card-title" id="npr-title">${icon('coins', { size: 18 })}Fiyat ve platformlar</h2>
          </header>
          <div class="card-body stack">
            <div class="field">
              <label class="label" for="new-price">Satış fiyatı <span class="opt">(isteğe bağlı)</span></label>
              <div class="input-wrap">
                <input id="new-price" class="input input-price" type="text" inputmode="numeric" autocomplete="off" placeholder="ör. 32.500" value="${draftPrice}" data-price />
                <span class="input-suffix">TL</span>
              </div>
              <p class="hint" data-price-hint>Boş bırakabilirsiniz; ilan oluşunca piyasa araştırmasıyla belirleyebilirsiniz.</p>
            </div>
            <div class="field">
              <span class="label" id="new-plat-l">Yayınlanacak platformlar</span>
              <div class="toggle-chips" role="group" aria-labelledby="new-plat-l" data-platforms>
                ${['sahibinden', 'letgo'].map((p) => html`
                  <button type="button" class="toggle-chip" data-platform="${p}" aria-pressed="true">
                    <span class="tc-check">${icon('check', { size: 13, strokeWidth: 3 })}</span>
                    <i class="pdot pdot-${p}" aria-hidden="true"></i>${platformName(p)}
                  </button>`)}
              </div>
              <p class="field-error" data-plat-err hidden>En az bir platform seçin.</p>
            </div>
          </div>
        </section>

        <div class="new-submit">
          <button type="submit" class="btn btn-primary btn-lg btn-block btn-magic" data-submit>
            ${icon('sparkles', { size: 20 })}<span>Yapay zekâ ile ilan oluştur</span>
          </button>
          <div class="progress is-determinate" data-progress hidden><span style="width:0%"></span></div>
          <p class="hint center" data-submit-hint>Oluşturma genellikle birkaç saniye sürer; sonra her şeyi düzenleyebilirsiniz.</p>
          <button type="button" class="link-btn small center-block" data-plain>Yapay zekâ kullanmadan boş taslak oluştur</button>
        </div>
      </div>
    </form>`.s;

  const form = $('form', root);
  const fileInput = $('[data-file]', root);
  const dropzone = $('[data-dropzone]', root);
  const thumbs = $('[data-thumbs]', root);
  const notes = $('[data-notes]', root);
  const price = $('[data-price]', root);
  const submitBtn = $('[data-submit]', root);
  const progress = $('[data-progress]', root);
  const selected = new Set(['sahibinden', 'letgo']);
  autosize(notes);

  // --- yapay zekâ ve platform varsayılanları
  getStatus().then((s) => {
    if (!ctx.alive() || !s) return;
    status = s;
    const enabled = Object.entries(s.platforms || {}).filter(([, v]) => v.enabled).map(([k]) => k);
    if (enabled.length) {
      selected.clear();
      enabled.forEach((p) => selected.add(p));
      renderPlatforms();
    }
    if (!s.ai || !s.ai.configured) {
      $('[data-ai-note]', root).innerHTML = callout({
        tone: 'warning',
        title: 'Yapay zekâ ayarlı değil',
        text: 'Notlarınızdan basit bir taslak hazırlanır; güçlü başlık ve açıklama için bir yapay zekâ sağlayıcısı tanımlayın.',
        action: html`<a class="btn btn-sm" href="#/ayarlar?b=ai">Ayarla</a>`,
      }).s;
    }
  }).catch(() => {});

  function renderPlatforms() {
    for (const b of $$('[data-platform]', root)) b.setAttribute('aria-pressed', String(selected.has(b.dataset.platform)));
    $('[data-plat-err]', root).hidden = selected.size > 0;
  }

  // --- fotoğraflar
  function addFiles(list) {
    let skipped = 0;
    let big = 0;
    for (const f of list) {
      if (f.type && !f.type.startsWith('image/') && !/\.(heic|heif)$/i.test(f.name)) {
        skipped++;
        continue;
      }
      if (f.size > MAX_BYTES) {
        big++;
        continue;
      }
      files.push({ id: uid('f'), file: f, url: URL.createObjectURL(f) });
    }
    if (skipped) toast.warning(`${skipped} dosya fotoğraf olmadığı için eklenmedi.`);
    if (big) toast.warning(`${big} fotoğraf 25 MB sınırını aştığı için eklenmedi.`);
    renderThumbs();
  }

  function renderThumbs() {
    $('[data-count]', root).textContent = files.length ? `(${files.length})` : '';
    dropzone.classList.toggle('is-compact', files.length > 0);
    thumbs.innerHTML = html`${files.map((f, i) => html`
      <li class="thumb" data-id="${f.id}" draggable="true">
        <button type="button" class="thumb-img" data-view="${i}" aria-label="${i + 1}. fotoğrafı büyüt">
          <img src="${f.url}" alt="" data-fallback="${f.file.name}" />
        </button>
        ${i === 0 ? html`<span class="thumb-badge">Kapak</span>` : ''}
        <div class="thumb-actions">
          <button type="button" class="thumb-btn" data-move="-1" ${i === 0 ? 'disabled' : ''} aria-label="${i + 1}. fotoğrafı sola taşı">${icon('chevronLeft', { size: 16 })}</button>
          ${i !== 0 ? html`<button type="button" class="thumb-btn" data-cover aria-label="${i + 1}. fotoğrafı kapak yap" title="Kapak yap">${icon('star', { size: 15 })}</button>` : ''}
          <button type="button" class="thumb-btn" data-move="1" ${i === files.length - 1 ? 'disabled' : ''} aria-label="${i + 1}. fotoğrafı sağa taşı">${icon('chevronRight', { size: 16 })}</button>
          <button type="button" class="thumb-btn is-danger" data-remove aria-label="${i + 1}. fotoğrafı kaldır">${icon('trash', { size: 15 })}</button>
        </div>
      </li>`)}`.s;
  }

  fileInput.addEventListener('change', () => {
    addFiles([...fileInput.files]);
    fileInput.value = '';
  });
  ['dragenter', 'dragover'].forEach((t) => dropzone.addEventListener(t, (e) => {
    if (!e.dataTransfer || ![...e.dataTransfer.types].includes('Files')) return;
    e.preventDefault();
    dropzone.classList.add('is-over');
  }));
  ['dragleave', 'drop'].forEach((t) => dropzone.addEventListener(t, () => dropzone.classList.remove('is-over')));
  dropzone.addEventListener('drop', (e) => {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    addFiles([...e.dataTransfer.files]);
  });
  // Sayfanın herhangi bir yerine bırakılan dosyalar da eklensin
  const onWindowDrop = (e) => {
    if (e.dataTransfer && e.dataTransfer.files.length && !dropzone.contains(e.target)) {
      e.preventDefault();
      addFiles([...e.dataTransfer.files]);
    }
  };
  const onWindowDragOver = (e) => {
    if (e.dataTransfer && [...e.dataTransfer.types].includes('Files')) e.preventDefault();
  };
  ctx.scope.on(window, 'drop', onWindowDrop);
  ctx.scope.on(window, 'dragover', onWindowDragOver);
  ctx.scope.on(document, 'paste', (e) => {
    const items = [...((e.clipboardData && e.clipboardData.files) || [])].filter((f) => f.type.startsWith('image/'));
    if (items.length) {
      e.preventDefault();
      addFiles(items);
      toast.success(`${items.length} fotoğraf yapıştırıldı.`);
    }
  });

  const move = (from, to) => {
    if (to < 0 || to >= files.length) return;
    const [f] = files.splice(from, 1);
    files.splice(to, 0, f);
    renderThumbs();
  };

  thumbs.addEventListener('click', (e) => {
    const li = e.target.closest('.thumb');
    if (!li) return;
    const idx = files.findIndex((f) => f.id === li.dataset.id);
    if (e.target.closest('[data-remove]')) {
      URL.revokeObjectURL(files[idx].url);
      files.splice(idx, 1);
      renderThumbs();
      return;
    }
    const mv = e.target.closest('[data-move]');
    if (mv) {
      move(idx, idx + Number(mv.dataset.move));
      const again = $(`.thumb[data-id="${files[Math.max(0, Math.min(files.length - 1, idx + Number(mv.dataset.move)))].id}"] [data-move="${mv.dataset.move}"]`, thumbs);
      if (again && !again.disabled) again.focus();
      return;
    }
    if (e.target.closest('[data-cover]')) {
      move(idx, 0);
      toast.success('Kapak fotoğrafı değiştirildi.');
      return;
    }
    if (e.target.closest('[data-view]')) openLightbox(files.map((f) => f.url), idx);
  });

  // masaüstü: sürükleyerek sıralama
  let dragId = null;
  thumbs.addEventListener('dragstart', (e) => {
    const li = e.target.closest('.thumb');
    if (!li) return;
    dragId = li.dataset.id;
    li.classList.add('is-dragging');
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', dragId);
  });
  thumbs.addEventListener('dragend', () => {
    dragId = null;
    $$('.thumb', thumbs).forEach((t) => t.classList.remove('is-dragging', 'is-drop'));
  });
  thumbs.addEventListener('dragover', (e) => {
    if (!dragId) return;
    e.preventDefault();
    const li = e.target.closest('.thumb');
    $$('.thumb', thumbs).forEach((t) => t.classList.toggle('is-drop', t === li && t.dataset.id !== dragId));
  });
  thumbs.addEventListener('drop', (e) => {
    if (!dragId) return;
    e.preventDefault();
    e.stopPropagation();
    const li = e.target.closest('.thumb');
    if (!li || li.dataset.id === dragId) return;
    move(files.findIndex((f) => f.id === dragId), files.findIndex((f) => f.id === li.dataset.id));
  });

  // --- notlar ve fiyat
  notes.addEventListener('input', () => {
    autosize(notes);
    store.set('new.notes', notes.value);
  });
  root.addEventListener('click', (e) => {
    const h = e.target.closest('[data-hint]');
    if (!h) return;
    const line = h.dataset.hint;
    const v = notes.value.replace(/\s+$/, '');
    notes.value = `${v}${v ? '\n' : ''}${line}`;
    autosize(notes);
    notes.focus();
    notes.setSelectionRange(notes.value.length, notes.value.length);
    store.set('new.notes', notes.value);
  });
  price.addEventListener('input', () => {
    price.removeAttribute('aria-invalid');
    store.set('new.price', price.value);
  });
  price.addEventListener('blur', () => {
    const v = parsePrice(price.value);
    if (v != null && !Number.isNaN(v)) price.value = priceInputValue(v);
    store.set('new.price', price.value);
  });

  $('[data-platforms]', root).addEventListener('click', (e) => {
    const b = e.target.closest('[data-platform]');
    if (!b) return;
    const p = b.dataset.platform;
    if (selected.has(p)) selected.delete(p);
    else selected.add(p);
    renderPlatforms();
  });

  // --- gönderim
  async function submit(generate) {
    if (busy) return;
    const priceVal = parsePrice(price.value);
    if (Number.isNaN(priceVal)) {
      price.setAttribute('aria-invalid', 'true');
      price.focus();
      toast.error('Fiyat sayı olmalı (ör. 32.500).');
      return;
    }
    if (!files.length && !notes.value.trim()) {
      toast.error('En az bir fotoğraf ya da ürün notu ekleyin.');
      notes.focus();
      return;
    }
    if (!selected.size) {
      $('[data-plat-err]', root).hidden = false;
      return;
    }
    busy = true;
    const fd = new FormData();
    fd.append('notes', notes.value.trim());
    fd.append('price', priceVal == null ? '' : String(Math.round(priceVal)));
    fd.append('platforms', [...selected].join(','));
    fd.append('generate', generate ? 'true' : 'false');
    files.forEach((f) => fd.append('photos', f.file, f.file.name));
    const label = $('span', submitBtn);
    const origLabel = label.textContent;
    submitBtn.disabled = true;
    submitBtn.setAttribute('aria-busy', 'true');
    submitBtn.classList.add('is-loading');
    progress.hidden = !files.length;
    label.textContent = files.length ? 'Fotoğraflar yükleniyor… %0' : 'Oluşturuluyor…';
    try {
      const res = await upload('/api/drafts', fd, {
        onProgress: (p) => {
          const pct = Math.round(p * 100);
          $('span', progress).style.width = `${pct}%`;
          label.textContent = pct < 100 ? `Fotoğraflar yükleniyor… %${pct}` : 'Hazırlanıyor…';
        },
      });
      store.remove('new.notes');
      store.remove('new.price');
      files.forEach((f) => URL.revokeObjectURL(f.url));
      files.length = 0;
      if (res.job) trackJob(res.job);
      toast.success(generate ? 'Taslak oluşturuldu; yapay zekâ ilanı yazıyor.' : 'Taslak oluşturuldu.');
      navigate(`#/ilan/${enc(res.draft.id)}${res.job ? `?is=${enc(res.job.id)}` : ''}`, { force: true });
    } catch (e) {
      toast.error(e.message || 'Taslak oluşturulamadı.');
      label.textContent = origLabel;
      submitBtn.disabled = false;
      submitBtn.removeAttribute('aria-busy');
      submitBtn.classList.remove('is-loading');
      progress.hidden = true;
      busy = false;
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    submit(true);
  });
  $('[data-plain]', root).addEventListener('click', () => submit(false));

  renderThumbs();
  ctx.scope.cleanup(() => files.forEach((f) => URL.revokeObjectURL(f.url)));

  return {
    isDirty: () => !busy && files.length > 0,
    leaveMessage: 'Seçtiğiniz fotoğraflar henüz gönderilmedi. Sayfadan çıkarsanız kaybolacaklar (notlarınız saklanır).',
  };
}

