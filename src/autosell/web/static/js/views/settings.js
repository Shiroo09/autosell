// Ayarlar: her bölüm kendi "Kaydet" düğmesiyle yalnızca kendi kısmını günceller (PUT /api/settings).
import { api } from '../api.js';
import { html, $, $$, isNum, platformName } from '../util.js';
import { icon } from '../icons.js';
import { toast, showError, confirmDialog, errorState, setBusy, callout } from '../ui.js';
import { replaceQuery } from '../router.js';
import { jobCard, trackJob } from '../jobs.js';
import { invalidateStatus, getStatus } from '../state.js';
import { themePref, setThemePref } from '../theme.js';

// ---------------------------------------------------------------- alan tanımları

const OPENAI_URLS = [
  ['https://betaapiv2.llmapi.art/v1', 'Varsayılan sunucu'],
  ['https://api.openai.com/v1', 'OpenAI'],
  ['https://openrouter.ai/api/v1', 'OpenRouter'],
  ['http://localhost:11434/v1', 'Ollama (yerel)'],
  ['http://localhost:1234/v1', 'LM Studio (yerel)'],
];
const CLAUDE_MODELS = [
  ['claude-opus-5-5', 'En yüksek kalite (önerilen)'],
  ['claude-sonnet-5-5', 'Hızlı ve dengeli'],
  ['claude-haiku-4-5', 'En hızlı ve ekonomik'],
];
const isOpenAI = (v) => v.provider === 'openai';
const isClaude = (v) => v.provider === 'claude';

const AI_FIELDS = [
  { key: 'provider', type: 'segmented', label: 'Sağlayıcı', options: [['openai', 'OpenAI uyumlu'], ['claude', 'Claude (Anthropic)']], hint: 'OpenAI uyumlu seçenek OpenAI, OpenRouter, Ollama, LM Studio gibi sunucularla çalışır.' },
  { key: 'openai_base_url', type: 'text', label: 'Sunucu adresi (base URL)', list: OPENAI_URLS, quick: true, placeholder: 'https://…/v1', showIf: isOpenAI, mono: true, inputmode: 'url' },
  { key: 'openai_model', type: 'text', label: 'Model', placeholder: 'ör. muse-spark-1.3', showIf: isOpenAI, models: true, mono: true },
  { key: 'openai_api_key', type: 'secret', label: 'API anahtarı', secret: 'ai.openai_api_key', env: 'OPENAI_API_KEY', showIf: isOpenAI, hint: 'Ollama / LM Studio gibi yerel sunucular için boş bırakılabilir.' },
  { key: 'openai_vision', type: 'switch', label: 'Model fotoğrafları görebiliyor', hint: 'Kapalıysa ilanlar yalnızca notlarınızdan yazılır.', showIf: isOpenAI },
  { key: 'claude_model', type: 'text', label: 'Model', list: CLAUDE_MODELS, placeholder: 'claude-opus-5-5', showIf: isClaude, models: true, mono: true },
  { key: 'claude_effort', type: 'select', label: 'Düşünme düzeyi', options: [['low', 'Düşük — en hızlı'], ['medium', 'Orta'], ['high', 'Yüksek — önerilen'], ['xhigh', 'Çok yüksek'], ['max', 'En yüksek — en yavaş']], showIf: isClaude, hint: 'Yüksek düzey daha iyi ilan yazar ama daha uzun sürer.' },
  { key: 'claude_api_key', type: 'secret', label: 'API anahtarı', secret: 'ai.claude_api_key', env: 'ANTHROPIC_API_KEY', showIf: isClaude, placeholder: 'sk-ant-…' },
  { key: 'claude_fallback', type: 'switch', label: 'Reddedilen isteklerde yedek modelle dene', hint: 'Güvenlik filtresi bir isteği reddederse Anthropic’in önerdiği modelle yeniden denenir.', showIf: isClaude },
  { key: 'max_photos', type: 'number', label: 'Yapay zekâya gönderilecek en fazla fotoğraf', min: 0, max: 20, step: 1, int: true, hint: 'Daha fazla fotoğraf daha isabetli analiz, ama daha yüksek maliyet demek.' },
  { key: 'web_research', type: 'switch', label: 'Fırsatları web’de güncel fiyatlarla doğrula', hint: 'Yalnızca Claude ile çalışır; ek maliyet oluşturabilir.' },
];

const SELLER_FIELDS = [
  { row: [
    { key: 'city', type: 'text', label: 'İl', placeholder: 'ör. İstanbul', required: true, autocomplete: 'address-level1' },
    { key: 'district', type: 'text', label: 'İlçe', placeholder: 'ör. Kadıköy', required: true, autocomplete: 'address-level2' },
  ] },
  { key: 'neighborhood', type: 'text', label: 'Mahalle', placeholder: 'ör. Moda Mah.', optional: true },
  { key: 'seller_type', type: 'text', label: 'Satıcı türü', list: [['Sahibinden', ''], ['Mağazadan', ''], ['Galeriden', '']], hint: 'Çoğu kişisel satış için “Sahibinden”.' },
  { key: 'negotiable', type: 'switch', label: 'Pazarlık payı var' },
  { key: 'allow_trade', type: 'switch', label: 'Takasa açığım' },
  { key: 'delivery_note', type: 'textarea', label: 'Teslimat notu', rows: 2, hint: 'Açıklamalarda teslimat bilgisi olarak kullanılır.' },
  { key: 'signature', type: 'textarea', label: 'İmza', rows: 2, optional: true, hint: 'Her açıklamanın sonuna eklenir (telefon numarası yazmayın; siteler iletişim bilgisine izin vermez).' },
];

const WRITING_FIELDS = [
  { key: 'title_style', type: 'segmented', label: 'Başlık biçimi', options: [['title', 'Baş Harfler Büyük'], ['sentence', 'Cümle düzeni'], ['upper', 'TÜMÜ BÜYÜK']], hint: 'Arama sonuçlarında en okunaklısı genellikle “Baş Harfler Büyük”tür.' },
  { key: 'tone', type: 'segmented', label: 'Anlatım tonu', options: [['dengeli', 'Dengeli'], ['samimi', 'Samimi'], ['profesyonel', 'Profesyonel']] },
  { key: 'extra_instructions', type: 'textarea', label: 'Ek talimatlar', rows: 3, optional: true, placeholder: 'ör. Açıklamanın sonuna “Kargo ücreti alıcıya aittir.” cümlesini ekle.', hint: 'Yapay zekânın her ilanda uygulayacağı kurallar.' },
];

const platformFields = (p) => [
  { key: 'enabled', type: 'switch', label: 'Etkin', hint: 'Yeni ilanlarda varsayılan olarak seçili gelir.' },
  { key: 'auto_publish', type: 'switch', label: 'Otomatik yayınla', danger: true, hint: 'Açıkken form doldurulduktan sonra son “Yayınla” adımı onay beklemeden tıklanır. Önce birkaç ilanı onaylı modda deneyin.' },
  { row: [
    { key: 'title_max', type: 'number', label: 'Başlık sınırı', min: 20, max: 200, int: true, suffix: 'karakter' },
    { key: 'description_max', type: 'number', label: 'Açıklama sınırı', min: 200, max: 20000, int: true, suffix: 'karakter' },
  ] },
  { key: 'use_emoji', type: 'switch', label: 'Başlık ve açıklamada emoji kullan', hint: p === 'sahibinden' ? 'Sahibinden emojiye genellikle izin vermez.' : '' },
  { advanced: [
    { key: 'home_url', type: 'text', label: 'Ana sayfa', mono: true, inputmode: 'url' },
    { key: 'login_url', type: 'text', label: 'Giriş sayfası', mono: true, inputmode: 'url' },
    { key: 'post_url', type: 'text', label: 'İlan verme sayfası', mono: true, optional: true, inputmode: 'url', hint: 'Boşsa ana sayfadaki “İlan Ver” düğmesi kullanılır.' },
    { key: 'search_url_template', type: 'text', label: 'Arama bağlantısı şablonu', mono: true, hint: '{q} arama kelimesiyle değiştirilir.' },
    { key: 'newest_sort_param', type: 'text', label: 'En yeni sıralama parametresi', mono: true, optional: true, placeholder: 'ör. sorting=date_desc' },
    { key: 'listing_url_patterns', type: 'lines', label: 'İlan bağlantısı kalıpları', rows: 3, hint: 'Her satıra bir düzenli ifade; ilk grup ilan numarasıdır.' },
    { key: 'card_selectors', type: 'kv', label: 'Arama sonucu kart seçicileri', rows: 6, hint: 'Her satıra anahtar=CSS seçici (card, title, price, location, date, image, id_attr).' },
  ] },
];

const BROWSER_FIELDS = [
  { key: 'headless', type: 'switch', label: 'Görünmez mod', hint: 'Tarayıcı penceresi gösterilmez. Giriş ve doğrulama adımlarını panelden “Tarayıcıyı buradan kontrol et” ile yapabilirsiniz.' },
  { key: 'channel', type: 'select', label: 'Tarayıcı', options: [['', 'Dahili Chromium (önerilen)'], ['chrome', 'Google Chrome (kurulu)'], ['msedge', 'Microsoft Edge (kurulu)']] },
  { key: 'executable_path', type: 'text', label: 'Tarayıcı dosya yolu', optional: true, mono: true, hint: 'Yalnızca özel bir tarayıcı kullanacaksanız.' },
  { key: 'use_ai_agent', type: 'switch', label: 'Takılınca yapay zekâ ajanı kullan', hint: 'Site yapısı değiştiğinde yapay zekâ sayfayı inceleyip adım adım ilerler.' },
  { advanced: [
    { row: [
      { key: 'slow_mo_ms', type: 'number', label: 'Yavaşlatma', min: 0, max: 2000, int: true, suffix: 'ms' },
      { key: 'agent_max_steps', type: 'number', label: 'Ajan adım sınırı', min: 1, max: 100, int: true },
    ] },
    { row: [
      { key: 'min_delay_ms', type: 'number', label: 'Eylemler arası en az bekleme', min: 0, max: 10000, int: true, suffix: 'ms' },
      { key: 'max_delay_ms', type: 'number', label: 'Eylemler arası en çok bekleme', min: 0, max: 20000, int: true, suffix: 'ms' },
    ] },
    { key: 'human_timeout_s', type: 'number', label: 'Sizi bekleme süresi', min: 30, max: 7200, int: true, suffix: 'sn', hint: 'Giriş, SMS kodu, onay gibi adımlar için en fazla bekleme.' },
  ] },
];

const MARKET_FIELDS = [
  { row: [
    { key: 'negotiation_pct', type: 'number', label: 'Alışta pazarlık indirimi', min: 0, max: 50, step: 0.5, suffix: '%', hint: 'Satıcıdan beklenen indirim; alış fiyatı buna göre hesaplanır.' },
    { key: 'commission_pct', type: 'number', label: 'Satış komisyonu', min: 0, max: 50, step: 0.5, suffix: '%', hint: 'Satarken ödenen komisyon.' },
  ] },
  { row: [
    { key: 'fixed_cost', type: 'number', label: 'Sabit masraf', min: 0, step: 50, suffix: 'TL', hint: 'Kargo, yol vb. her satıştaki masraf.' },
    { key: 'resale_percentile', type: 'number', label: 'Hedef satış yüzdeliği', min: 5, max: 95, step: 1, hint: 'Emsaller içinde satış fiyatının yeri (50 = medyan, 45 = biraz altı: daha hızlı satış).' },
  ] },
  { row: [
    { key: 'min_comps', type: 'number', label: 'En az emsal sayısı', min: 1, max: 50, int: true, hint: 'Daha az emsalde fırsat sayılmaz.' },
    { key: 'comp_days', type: 'number', label: 'Emsal geçerlilik süresi', min: 1, max: 365, int: true, suffix: 'gün' },
  ] },
  { advanced: [
    { row: [
      { key: 'default_interval_min', type: 'number', label: 'Varsayılan tarama aralığı', min: 1, int: true, suffix: 'dk' },
      { key: 'min_interval_min', type: 'number', label: 'En kısa tarama aralığı', min: 1, int: true, suffix: 'dk' },
    ] },
    { row: [
      { key: 'max_pages', type: 'number', label: 'Taranacak sayfa sayısı', min: 1, max: 10, int: true },
      { key: 'fetch_details', type: 'number', label: 'Detayı okunacak aday', min: 0, max: 20, int: true, hint: 'Her taramada açıklaması okunacak en iyi aday sayısı.' },
    ] },
    { key: 'ai_evaluations', type: 'number', label: 'Yapay zekâ değerlendirmesi', min: 0, max: 20, int: true, hint: 'Her taramada yapay zekâya sorulacak en iyi fırsat sayısı.' },
  ] },
];

const NOTIFY_FIELDS = [
  { key: 'telegram_token', type: 'secret', label: 'Telegram bot anahtarı (token)', secret: 'notify.telegram_token', env: 'TELEGRAM_BOT_TOKEN', placeholder: '123456:ABC…' },
  { key: 'telegram_chat_id', type: 'text', label: 'Sohbet kimliği (chat id)', placeholder: 'ör. 123456789', mono: true },
  { key: 'min_score', type: 'number', label: 'Bildirim için en düşük fırsat puanı', min: 0, max: 100, step: 1, hint: 'Bu puanın üzerindeki fırsatlar Telegram’a gönderilir.' },
];

const WEB_FIELDS = [
  { key: 'password', type: 'secret', label: 'Panel şifresi', secret: 'web.password', env: 'AUTOSELL_PANEL_PASSWORD', autocomplete: 'new-password', placeholder: 'Yeni şifre' },
];

const SECTIONS = [
  { id: 'ai', title: 'Yapay Zekâ', icon: 'bot', desc: 'İlan metinlerini yazan ve fırsatları değerlendiren model', units: [{ key: 'ai', fields: AI_FIELDS, actions: ['test-ai'] }] },
  { id: 'seller', title: 'Satıcı Profili', icon: 'user', desc: 'Konum, pazarlık ve teslimat bilgileri', units: [{ key: 'seller', fields: SELLER_FIELDS }] },
  { id: 'writing', title: 'Yazım', icon: 'type', desc: 'Başlık biçimi ve anlatım tonu', units: [{ key: 'writing', fields: WRITING_FIELDS }] },
  { id: 'platforms', title: 'Platformlar', icon: 'store', desc: 'Sahibinden ve Letgo: sınırlar, otomatik yayın, giriş', units: [
    { key: 'sahibinden', title: 'Sahibinden', fields: platformFields('sahibinden'), actions: ['login'] },
    { key: 'letgo', title: 'Letgo', fields: platformFields('letgo'), actions: ['login'] },
  ] },
  { id: 'browser', title: 'Tarayıcı', icon: 'browser', desc: 'Otomasyon tarayıcısı ve bekleme süreleri', units: [{ key: 'browser', fields: BROWSER_FIELDS }] },
  { id: 'market', title: 'Fırsat Avcısı', icon: 'target', desc: 'Kâr hesabı, maliyetler ve tarama sınırları', units: [{ key: 'market', fields: MARKET_FIELDS }] },
  { id: 'notify', title: 'Bildirimler', icon: 'bell', desc: 'Yeni fırsatlar için Telegram bildirimi', units: [{ key: 'notify', fields: NOTIFY_FIELDS, actions: ['test-telegram'] }] },
  { id: 'web', title: 'Panel Güvenliği', icon: 'lock', desc: 'Telefondan erişim için panel şifresi', units: [{ key: 'web', fields: WEB_FIELDS, actions: ['logout'] }] },
];

const flatFields = (fields) => fields.flatMap((f) => (f.row ? f.row : f.advanced ? flatFields(f.advanced) : [f]));

// ---------------------------------------------------------------- görünüm

export async function mount(root, ctx) {
  let settings = null;
  const units = new Map(); // key → { def, values, original, secrets: {field: string|null} , loginCard }
  const open = new Set([ctx.query.get('b') || 'ai']);
  const advOpen = new Set();

  root.innerHTML = html`
    <header class="page-head">
      <div class="page-head-main">
        <h1 class="page-title">Ayarlar</h1>
        <p class="page-sub">Her bölüm kendi “Kaydet” düğmesiyle ayrı kaydedilir.</p>
      </div>
    </header>
    <div class="settings" data-settings><div class="view-loading"><span class="spinner"></span></div></div>`.s;
  const $root = $('[data-settings]', root);

  function valueOf(section, key) {
    const v = settings[section] ? settings[section][key] : undefined;
    return v;
  }

  function initUnit(def) {
    const src = settings[def.key] || {};
    const values = {};
    for (const f of flatFields(def.fields)) {
      if (f.type === 'secret') continue;
      const v = src[f.key];
      if (f.type === 'lines') values[f.key] = (v || []).join('\n');
      else if (f.type === 'kv') values[f.key] = Object.entries(v || {}).map(([k, x]) => `${k}=${x}`).join('\n');
      else values[f.key] = v;
    }
    const prev = units.get(def.key);
    units.set(def.key, { def, values, original: JSON.stringify(values), secrets: {}, models: prev ? prev.models : null, loginCard: prev ? prev.loginCard : null });
  }

  const unitDirty = (u) => JSON.stringify(u.values) !== u.original || Object.values(u.secrets).some((v) => v !== undefined && v !== null);
  const anyDirty = () => [...units.values()].some(unitDirty);

  // --- alan çizimi
  function fieldHtml(u, f) {
    const id = `st-${u.def.key}-${f.key}`;
    const v = u.values[f.key];
    const hidden = f.showIf && !f.showIf(u.values);
    const hint = f.hint ? html`<p class="hint" id="${id}-h">${f.hint}</p>` : '';
    const describedBy = f.hint ? `${id}-h` : '';
    const wrap = (inner, cls = '') => html`<div class="field ${cls}" data-field-wrap="${f.key}" ${hidden ? 'hidden' : ''}>${inner}</div>`;
    const label = html`<label class="label" for="${id}">${f.label}${f.optional ? html` <span class="opt">(isteğe bağlı)</span>` : ''}</label>`;
    switch (f.type) {
      case 'switch':
        return wrap(html`
          <label class="switch ${f.danger ? 'is-danger' : ''}">
            <input type="checkbox" id="${id}" data-key="${f.key}" ${v ? 'checked' : ''} ${describedBy ? html`aria-describedby="${describedBy}"` : ''} />
            <span class="switch-track" aria-hidden="true"></span>
            <span class="switch-text"><span class="switch-label">${f.label}</span>${f.hint ? html`<span class="switch-hint" id="${id}-h">${f.hint}</span>` : ''}</span>
          </label>
          ${f.danger && v ? html`<p class="danger-note">${icon('zap', { size: 14 })}<span>Otomatik yayın açık.</span></p>` : ''}`, 'field-switch');
      case 'segmented':
        return wrap(html`
          <span class="label" id="${id}-l">${f.label}</span>
          <div class="segmented seg-wrap" role="radiogroup" aria-labelledby="${id}-l">
            ${f.options.map(([val, lbl]) => html`<label><input type="radio" name="${id}" value="${val}" data-key="${f.key}" ${String(v) === String(val) ? 'checked' : ''} /><span class="seg">${lbl}</span></label>`)}
          </div>${hint}`);
      case 'select':
        return wrap(html`${label}
          <select id="${id}" class="select" data-key="${f.key}" ${describedBy ? html`aria-describedby="${describedBy}"` : ''}>
            ${f.options.map(([val, lbl]) => html`<option value="${val}" ${String(v ?? '') === String(val) ? 'selected' : ''}>${lbl}</option>`)}
          </select>${hint}`);
      case 'number':
        return wrap(html`${label}
          <div class="input-wrap">
            <input id="${id}" class="input" type="number" inputmode="${f.int ? 'numeric' : 'decimal'}" data-key="${f.key}" value="${v ?? ''}" ${isNum(f.min) ? html`min="${f.min}"` : ''} ${isNum(f.max) ? html`max="${f.max}"` : ''} step="${f.step || (f.int ? 1 : 'any')}" ${describedBy ? html`aria-describedby="${describedBy}"` : ''} />
            ${f.suffix ? html`<span class="input-suffix">${f.suffix}</span>` : ''}
          </div>${hint}`);
      case 'textarea':
      case 'lines':
      case 'kv':
        return wrap(html`${label}
          <textarea id="${id}" class="textarea ${f.type !== 'textarea' ? 'is-mono' : ''}" rows="${f.rows || 3}" data-key="${f.key}" placeholder="${f.placeholder || ''}" spellcheck="${f.type === 'textarea'}" ${describedBy ? html`aria-describedby="${describedBy}"` : ''}>${v ?? ''}</textarea>${hint}`);
      case 'secret': {
        const meta = (settings._secrets || {})[f.secret] || {};
        const masked = valueOf(u.def.key, f.key) || '';
        const edit = u.secrets[f.key];
        const state = edit === '' ? 'clear' : meta.set ? 'set' : meta.from_env ? 'env' : 'none';
        const placeholder = state === 'set' ? `${masked} — kayıtlı (değiştirmek için yazın)` : state === 'env' ? `${f.env} ortam değişkeninden okunuyor` : f.placeholder || 'Girilmedi';
        return wrap(html`${label}
          <div class="input-row">
            <div class="input-wrap grow">
              <input id="${id}" class="input is-mono" type="password" data-secret="${f.key}" value="${edit && edit !== '' ? edit : ''}" placeholder="${state === 'clear' ? 'Kaydedince silinecek' : placeholder}" autocomplete="${f.autocomplete || 'off'}" spellcheck="false" ${describedBy ? html`aria-describedby="${describedBy}"` : ''} />
              <button type="button" class="input-btn" data-reveal="${id}" aria-label="Göster" aria-pressed="false">${icon('eye', { size: 18 })}</button>
            </div>
            ${state === 'set' ? html`<button type="button" class="btn btn-ghost btn-danger" data-clear-secret="${f.key}">Kaldır</button>` : ''}
            ${state === 'clear' ? html`<button type="button" class="btn btn-ghost" data-keep-secret="${f.key}">Geri al</button>` : ''}
          </div>
          <p class="hint">${state === 'set' ? 'Boş bırakırsanız kayıtlı değer korunur.' : state === 'env' ? 'Buraya yazarsanız ortam değişkeninin yerine bu kullanılır.' : state === 'clear' ? 'Kaydettiğinizde bu değer silinecek.' : ''} ${f.hint || ''}</p>`);
      }
      default: {
        const listId = f.list ? `${id}-list` : '';
        const models = f.models && u.models && u.models.forKey === f.key ? u.models.list : null;
        return wrap(html`${label}
          <div class="input-row">
            <input id="${id}" class="input ${f.mono ? 'is-mono' : ''}" type="text" data-key="${f.key}" value="${v ?? ''}" placeholder="${f.placeholder || ''}" ${listId || models ? html`list="${id}-list"` : ''} autocomplete="${f.autocomplete || 'off'}" ${f.inputmode ? html`inputmode="${f.inputmode}"` : ''} spellcheck="false" ${describedBy ? html`aria-describedby="${describedBy}"` : ''} />
            ${f.models ? html`<button type="button" class="btn" data-list-models="${f.key}">${icon('list', { size: 17 })}<span>Modelleri listele</span></button>` : ''}
          </div>
          ${listId || models ? html`<datalist id="${id}-list">${(f.list || []).concat((models || []).map((m) => [m, ''])).map(([val, lbl]) => html`<option value="${val}">${lbl}</option>`)}</datalist>` : ''}
          ${f.quick ? html`<div class="chips quick-picks">${f.list.map(([val, lbl]) => html`<button type="button" class="chip chip-add ${v === val ? 'is-added' : ''}" data-pick="${f.key}" data-value="${val}">${lbl}</button>`)}</div>` : ''}
          ${models ? html`
            <div class="model-list" role="listbox" aria-label="Sunucudaki modeller">
              <div class="model-list-head"><span class="small"><strong>${models.length}</strong> model bulundu</span><input class="input input-sm" type="search" placeholder="Modellerde ara…" data-model-filter aria-label="Modellerde ara" /></div>
              <div class="model-items">${models.map((m) => html`<button type="button" role="option" class="model-item ${m === v ? 'is-on' : ''}" aria-selected="${m === v}" data-pick="${f.key}" data-value="${m}">${m === v ? icon('check', { size: 14 }) : ''}<span>${m}</span></button>`)}</div>
            </div>` : ''}
          ${hint}`);
      }
    }
  }

  function fieldsHtml(u, fields) {
    return html`${fields.map((f) => {
      if (f.row) return html`<div class="grid-2">${f.row.map((x) => fieldHtml(u, x))}</div>`;
      if (f.advanced) {
        const key = `${u.def.key}`;
        const isOpen = advOpen.has(key);
        return html`
          <div class="advanced ${isOpen ? 'is-open' : ''}">
            <button type="button" class="advanced-toggle" data-adv="${key}" aria-expanded="${isOpen}">${icon(isOpen ? 'chevronUp' : 'chevronDown', { size: 16 })}<span>Gelişmiş</span></button>
            <div class="advanced-body stack" ${isOpen ? '' : 'hidden'}>${fieldsHtml(u, f.advanced)}</div>
          </div>`;
      }
      return fieldHtml(u, f);
    })}`;
  }

  function unitHtml(u) {
    const d = u.def;
    const dirty = unitDirty(u);
    const isPlatform = d.key === 'sahibinden' || d.key === 'letgo';
    return html`
      <form class="set-unit ${isPlatform ? 'is-sub' : ''}" data-unit="${d.key}" novalidate>
        ${d.title ? html`<h3 class="set-unit-title"><i class="pdot pdot-${d.key}"></i>${d.title}</h3>` : ''}
        ${d.key === 'web' ? html`${callout({ tone: 'info', icon: 'phone', title: 'Telefondan erişim', text: html`Paneli aynı Wi-Fi ağındaki telefonunuzdan açmak için şifre gereklidir. Şifreyi belirledikten sonra AutoSell’i <code>autosell panel --host 0.0.0.0</code> ile başlatın ve telefonunuzdan bilgisayarın yerel IP adresine girin (ör. <code>http://192.168.1.20:8000</code>).` })}` : ''}
        <div class="stack">${fieldsHtml(u, d.fields)}</div>
        <div class="set-job" data-unit-job></div>
        <footer class="set-foot">
          ${(d.actions || []).includes('test-ai') ? html`<button type="button" class="btn" data-test-ai>${icon('zap', { size: 17 })}<span>Bağlantıyı test et</span></button>` : ''}
          ${(d.actions || []).includes('test-telegram') ? html`<button type="button" class="btn" data-test-telegram>${icon('send', { size: 17 })}<span>Test mesajı gönder</span></button>` : ''}
          ${(d.actions || []).includes('login') ? html`<button type="button" class="btn" data-login="${d.key}">${icon('key', { size: 17 })}<span>${platformName(d.key)} hesabına giriş yap</span></button>` : ''}
          ${(d.actions || []).includes('logout') && ((settings._secrets || {})['web.password'] || {}).set ? html`<button type="button" class="btn btn-ghost" data-logout>${icon('logout', { size: 17 })}<span>Çıkış yap</span></button>` : ''}
          <span class="grow"></span>
          ${dirty ? html`<span class="dirty-note">${icon('pencil', { size: 14 })}Kaydedilmedi</span>` : ''}
          <button type="submit" class="btn btn-primary" data-save ${dirty ? '' : 'disabled'}>${icon('check', { size: 17 })}<span>Kaydet</span></button>
        </footer>
      </form>`;
  }

  function renderUnit(key) {
    const u = units.get(key);
    const node = $(`[data-unit="${key}"]`, root);
    if (!u || !node) return;
    const focused = document.activeElement && node.contains(document.activeElement) ? document.activeElement.id : null;
    const tmp = document.createElement('div');
    tmp.innerHTML = unitHtml(u).s;
    const fresh = tmp.firstElementChild;
    const jobSlot = $('[data-unit-job]', node);
    node.replaceWith(fresh);
    if (jobSlot && jobSlot.childElementCount) $('[data-unit-job]', fresh).replaceWith(jobSlot);
    if (focused) {
      const f = document.getElementById(focused);
      if (f) f.focus({ preventScroll: true });
    }
  }

  function updateFoot(key) {
    const u = units.get(key);
    const node = $(`[data-unit="${key}"]`, root);
    if (!u || !node) return;
    const dirty = unitDirty(u);
    const btn = $('[data-save]', node);
    if (btn && btn.dataset.busy !== '1') btn.disabled = !dirty;
    let note = $('.dirty-note', node);
    if (dirty && !note) {
      note = document.createElement('span');
      note.className = 'dirty-note';
      note.innerHTML = html`${icon('pencil', { size: 14 })}Kaydedilmedi`.s;
      btn.before(note);
    } else if (!dirty && note) note.remove();
    const section = node.closest('[data-section]');
    if (section) {
      const any = $$('[data-unit]', section).some((n) => unitDirty(units.get(n.dataset.unit)));
      $('.set-dirty-dot', section).hidden = !any;
    }
  }

  function applyVisibility(key) {
    const u = units.get(key);
    const node = $(`[data-unit="${key}"]`, root);
    for (const f of flatFields(u.def.fields)) {
      if (!f.showIf) continue;
      const w = $(`[data-field-wrap="${f.key}"]`, node);
      if (w) w.hidden = !f.showIf(u.values);
    }
  }

  function render() {
    $root.innerHTML = html`
      ${SECTIONS.map((s) => html`
        <section class="set-section card ${open.has(s.id) ? 'is-open' : ''}" data-section="${s.id}" id="ayar-${s.id}">
          <h2 class="set-head-h">
            <button type="button" class="set-head" data-toggle="${s.id}" aria-expanded="${open.has(s.id)}" aria-controls="ayar-${s.id}-body">
              <span class="icon-tile">${icon(s.icon, { size: 19 })}</span>
              <span class="set-head-text"><span class="set-title">${s.title}</span><span class="set-desc">${s.desc}</span></span>
              <span class="set-dirty-dot" hidden title="Kaydedilmemiş değişiklik"></span>
              ${icon('chevronDown', { size: 20, cls: 'set-chev' })}
            </button>
          </h2>
          <div class="set-body" id="ayar-${s.id}-body" ${open.has(s.id) ? '' : 'hidden'}>
            ${s.units.map((d) => unitHtml(units.get(d.key)))}
          </div>
        </section>`)}
      <section class="set-section card is-open" data-section="appearance">
        <div class="set-head is-static">
          <span class="icon-tile">${icon('sun', { size: 19 })}</span>
          <span class="set-head-text"><span class="set-title">Görünüm</span><span class="set-desc">Bu cihaz için tema tercihi</span></span>
        </div>
        <div class="set-body">
          <div class="set-unit">
            <div class="segmented seg-wrap" role="radiogroup" aria-label="Tema">
              ${[['system', 'Sistem', 'monitor'], ['light', 'Açık', 'sun'], ['dark', 'Koyu', 'moon']].map(([val, lbl, ic]) => html`<label><input type="radio" name="theme" value="${val}" data-theme-pref ${themePref() === val ? 'checked' : ''} /><span class="seg">${icon(ic, { size: 16 })}${lbl}</span></label>`)}
            </div>
          </div>
        </div>
      </section>
      <p class="muted small center set-version" data-version></p>`.s;
    getStatus().then((s) => {
      const v = $('[data-version]', root);
      if (v && s) v.textContent = `AutoSell ${s.version} · ${s.ai && s.ai.configured ? `Yapay zekâ: ${s.ai.description}` : 'Yapay zekâ ayarlı değil'}`;
    }).catch(() => {});
  }

  // --- kaydetme
  function collectPatch(u) {
    const patch = {};
    for (const f of flatFields(u.def.fields)) {
      if (f.type === 'secret') {
        const s = u.secrets[f.key];
        if (s !== undefined && s !== null) patch[f.key] = s;
        continue;
      }
      let v = u.values[f.key];
      if (f.type === 'number') {
        if (v === '' || v == null || !Number.isFinite(Number(v))) throw Object.assign(new Error(`“${f.label}” için geçerli bir sayı girin.`), { field: f.key });
        v = f.int ? Math.round(Number(v)) : Number(v);
        if (isNum(f.min) && v < f.min) throw Object.assign(new Error(`“${f.label}” en az ${f.min} olmalı.`), { field: f.key });
        if (isNum(f.max) && v > f.max) throw Object.assign(new Error(`“${f.label}” en fazla ${f.max} olabilir.`), { field: f.key });
      } else if (f.type === 'lines') {
        v = String(v || '').split('\n').map((x) => x.trim()).filter(Boolean);
      } else if (f.type === 'kv') {
        const obj = {};
        for (const line of String(v || '').split('\n')) {
          const t = line.trim();
          if (!t) continue;
          const i = t.indexOf('=');
          if (i <= 0) throw Object.assign(new Error(`“${f.label}”: her satır anahtar=değer biçiminde olmalı (“${t.slice(0, 30)}”).`), { field: f.key });
          obj[t.slice(0, i).trim()] = t.slice(i + 1).trim();
        }
        v = obj;
      } else if (typeof v === 'string') {
        v = v.trim();
      }
      if (f.required && !v) throw Object.assign(new Error(`“${f.label}” boş bırakılamaz.`), { field: f.key });
      patch[f.key] = v;
    }
    return patch;
  }

  async function saveUnit(key, { quiet = false } = {}) {
    const u = units.get(key);
    if (!unitDirty(u)) return true;
    const node = $(`[data-unit="${key}"]`, root);
    let patch;
    try {
      patch = collectPatch(u);
    } catch (e) {
      toast.error(e.message);
      if (e.field) {
        const input = $(`[data-key="${e.field}"]`, node);
        if (input) {
          input.setAttribute('aria-invalid', 'true');
          input.focus();
        }
      }
      return false;
    }
    const btn = $('[data-save]', node);
    setBusy(btn, true, 'Kaydediliyor…');
    const newPassword = key === 'web' && typeof patch.password === 'string' && patch.password ? patch.password : null;
    try {
      settings = await api.put('/api/settings', { [key]: patch });
      if (newPassword) {
        try {
          await api.post('/api/login', { password: newPassword });
        } catch {
          /* giriş ekranı açılır */
        }
      }
      initUnit(u.def);
      renderUnit(key);
      updateFoot(key);
      invalidateStatus();
      getStatus({ force: true }).catch(() => {});
      if (!quiet) toast.success(key === 'web' ? (newPassword ? 'Panel şifresi kaydedildi. Telefondan bu şifreyle giriş yapabilirsiniz.' : 'Panel güvenliği güncellendi.') : 'Ayarlar kaydedildi.');
      return true;
    } catch (e) {
      showError(e);
      if (btn.isConnected) setBusy(btn, false);
      return false;
    }
  }

  async function saveAll() {
    for (const [key, u] of units) {
      if (unitDirty(u) && !(await saveUnit(key, { quiet: true }))) return false;
    }
    toast.success('Ayarlar kaydedildi.');
    return true;
  }

  // --- olaylar
  function onValue(t) {
    const unitEl = t.closest('[data-unit]');
    if (!unitEl) return;
    const u = units.get(unitEl.dataset.unit);
    if (!u) return;
    t.removeAttribute('aria-invalid');
    if (t.dataset.secret) {
      u.secrets[t.dataset.secret] = t.value === '' ? undefined : t.value;
    } else if (t.dataset.key) {
      const f = flatFields(u.def.fields).find((x) => x.key === t.dataset.key);
      if (!f) return;
      if (f.type === 'switch') u.values[f.key] = t.checked;
      else if (f.type === 'segmented') {
        if (!t.checked) return;
        u.values[f.key] = t.value;
      } else u.values[f.key] = t.value;
      if (f.type === 'switch' && f.danger) {
        renderUnit(u.def.key);
        updateFoot(u.def.key);
        return;
      }
    }
    applyVisibility(u.def.key);
    updateFoot(u.def.key);
  }

  root.addEventListener('input', (e) => {
    if (e.target.matches('[data-model-filter]')) {
      const q = e.target.value.trim().toLocaleLowerCase('tr');
      for (const b of $$('.model-item', e.target.closest('.model-list'))) b.hidden = q && !b.dataset.value.toLocaleLowerCase('tr').includes(q);
      return;
    }
    if (e.target.matches('input[type="text"], input[type="number"], input[type="password"], textarea')) onValue(e.target);
  });
  root.addEventListener('change', (e) => {
    if (e.target.matches('[data-theme-pref]')) {
      setThemePref(e.target.value);
      return;
    }
    if (e.target.matches('input[type="checkbox"], input[type="radio"], select')) onValue(e.target);
  });

  root.addEventListener('submit', (e) => {
    const form = e.target.closest('[data-unit]');
    if (!form) return;
    e.preventDefault();
    saveUnit(form.dataset.unit);
  });

  root.addEventListener('click', async (e) => {
    const t = e.target;
    const toggle = t.closest('[data-toggle]');
    if (toggle) {
      const id = toggle.dataset.toggle;
      const sec = toggle.closest('[data-section]');
      const isOpen = !open.has(id);
      if (isOpen) open.add(id);
      else open.delete(id);
      sec.classList.toggle('is-open', isOpen);
      toggle.setAttribute('aria-expanded', String(isOpen));
      $('.set-body', sec).hidden = !isOpen;
      replaceQuery(isOpen ? { b: id } : {});
      return;
    }
    const adv = t.closest('[data-adv]');
    if (adv) {
      const key = adv.dataset.adv;
      if (advOpen.has(key)) advOpen.delete(key);
      else advOpen.add(key);
      const box = adv.closest('.advanced');
      const isOpen = advOpen.has(key);
      box.classList.toggle('is-open', isOpen);
      adv.setAttribute('aria-expanded', String(isOpen));
      adv.innerHTML = html`${icon(isOpen ? 'chevronUp' : 'chevronDown', { size: 16 })}<span>Gelişmiş</span>`.s;
      $('.advanced-body', box).hidden = !isOpen;
      return;
    }
    const reveal = t.closest('[data-reveal]');
    if (reveal) {
      const input = document.getElementById(reveal.dataset.reveal);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      reveal.setAttribute('aria-pressed', String(show));
      reveal.setAttribute('aria-label', show ? 'Gizle' : 'Göster');
      reveal.innerHTML = icon(show ? 'eyeOff' : 'eye', { size: 18 }).s;
      return;
    }
    const clear = t.closest('[data-clear-secret]');
    if (clear) {
      const u = units.get(clear.closest('[data-unit]').dataset.unit);
      u.secrets[clear.dataset.clearSecret] = '';
      renderUnit(u.def.key);
      updateFoot(u.def.key);
      return;
    }
    const keep = t.closest('[data-keep-secret]');
    if (keep) {
      const u = units.get(keep.closest('[data-unit]').dataset.unit);
      u.secrets[keep.dataset.keepSecret] = undefined;
      renderUnit(u.def.key);
      updateFoot(u.def.key);
      return;
    }
    const pick = t.closest('[data-pick]');
    if (pick) {
      const u = units.get(pick.closest('[data-unit]').dataset.unit);
      u.values[pick.dataset.pick] = pick.dataset.value;
      renderUnit(u.def.key);
      updateFoot(u.def.key);
      return;
    }
    const lm = t.closest('[data-list-models]');
    if (lm) {
      listModels(lm);
      return;
    }
    if (t.closest('[data-test-ai]')) {
      testAi(t.closest('[data-test-ai]'));
      return;
    }
    if (t.closest('[data-test-telegram]')) {
      testTelegram(t.closest('[data-test-telegram]'));
      return;
    }
    const login = t.closest('[data-login]');
    if (login) {
      startLogin(login.dataset.login, login);
      return;
    }
    if (t.closest('[data-logout]')) {
      const ok = await confirmDialog({ title: 'Çıkış yapılsın mı?', message: 'Bu cihazda panel oturumu kapatılır; yeniden girmek için şifre gerekir.', confirmText: 'Çıkış yap' });
      if (!ok) return;
      try {
        await api.post('/api/logout');
        location.reload();
      } catch (err) {
        showError(err);
      }
      return;
    }
    if (t.closest('[data-action="retry"]')) load();
  });

  async function ensureSaved(key, why) {
    const u = units.get(key);
    if (!unitDirty(u)) return true;
    const saved = await saveUnit(key, { quiet: true });
    if (saved) toast.info(`Ayarlar ${why} önce kaydedildi.`);
    return saved;
  }

  async function listModels(btn) {
    const key = btn.dataset.listModels;
    if (!(await ensureSaved('ai', 'model listesi alınmadan'))) return;
    const target = $(`[data-list-models="${key}"]`, root) || btn;
    setBusy(target, true, 'Listeleniyor…');
    try {
      const r = await api('/api/settings/models');
      const list = (r.models || []).filter(Boolean);
      const u = units.get('ai');
      if (!list.length) {
        u.models = null;
        toast.info('Sağlayıcı model listesi döndürmedi; model adını elle yazın.', { title: r.provider ? `${r.provider} · ${r.current || ''}` : '' });
      } else {
        u.models = { forKey: key, list };
        toast.success(`${list.length} model bulundu. Listeden seçebilirsiniz.`);
      }
      renderUnit('ai');
      updateFoot('ai');
      const input = $(`[data-key="${key}"]`, root);
      if (input && list.length) input.focus({ preventScroll: true });
    } catch (e) {
      showError(e);
      const b = $(`[data-list-models="${key}"]`, root);
      if (b) setBusy(b, false);
    }
  }

  async function testAi(btn) {
    if (!(await ensureSaved('ai', 'test edilmeden'))) return;
    const b = $('[data-test-ai]', root) || btn;
    setBusy(b, true, 'Test ediliyor…');
    try {
      const r = await api.post('/api/settings/test-ai');
      toast.success(`Yanıt: “${r.answer || 'tamam'}”`, { title: `Bağlantı başarılı · ${r.provider}` });
    } catch (e) {
      toast.error(e.message || 'Bağlantı kurulamadı.', { title: 'Yapay zekâ testi başarısız' });
    } finally {
      if (b.isConnected) setBusy(b, false);
    }
  }

  async function testTelegram(btn) {
    if (!(await ensureSaved('notify', 'test edilmeden'))) return;
    const b = $('[data-test-telegram]', root) || btn;
    setBusy(b, true, 'Gönderiliyor…');
    try {
      await api.post('/api/settings/test-telegram');
      toast.success('Test mesajı gönderildi. Telegram’ı kontrol edin.');
    } catch (e) {
      toast.error(e.message || 'Mesaj gönderilemedi.', { title: 'Telegram testi başarısız' });
    } finally {
      if (b.isConnected) setBusy(b, false);
    }
  }

  async function startLogin(platform, btn) {
    setBusy(btn, true, 'Başlatılıyor…');
    try {
      const job = await api.post(`/api/platforms/${platform}/login`);
      trackJob(job);
      const u = units.get(platform);
      const slot = $(`[data-unit="${platform}"] [data-unit-job]`, root);
      if (u.loginCard) u.loginCard.stop();
      u.loginCard = jobCard(job, {
        onDone: (j) => {
          if (j.status === 'done') toast.success(`${platformName(platform)} oturumu açıldı ve kaydedildi.`);
        },
      });
      slot.replaceChildren(u.loginCard.el);
      toast.info('Açılan tarayıcıda hesabınıza giriş yapın; telefondaysanız “Tarayıcıyı buradan kontrol et”i kullanın.', { title: `${platformName(platform)} girişi` });
    } catch (e) {
      showError(e);
    } finally {
      if (btn.isConnected) setBusy(btn, false);
    }
  }

  async function load() {
    try {
      settings = await api('/api/settings', { signal: ctx.signal });
      if (!ctx.alive()) return;
      for (const s of SECTIONS) for (const d of s.units) initUnit(d);
      render();
      const target = ctx.query.get('b');
      if (target) {
        const sec = document.getElementById(`ayar-${target}`);
        if (sec) setTimeout(() => sec.scrollIntoView({ block: 'start', behavior: 'smooth' }), 60);
      }
    } catch (e) {
      if (e.name === 'AbortError' || !ctx.alive()) return;
      $root.innerHTML = html`<div class="card">${errorState(e)}</div>`.s;
    }
  }

  ctx.scope.cleanup(() => {
    for (const u of units.values()) if (u.loginCard) u.loginCard.stop();
  });

  await load();
  return {
    isDirty: anyDirty,
    save: saveAll,
    leaveMessage: 'Bazı ayar bölümlerinde kaydetmediğiniz değişiklikler var.',
  };
}

