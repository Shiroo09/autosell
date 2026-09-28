// Uzaktan tarayıcı kontrolü: bekleyen bir işin tarayıcı ekranını panelden izleyip dokunarak/yazarak yönetme.
import { api, enc } from './api.js';
import { html, el, $, $$, platformName, safeUrl } from './util.js';
import { icon } from './icons.js';
import { openSheet, toast, setBusy } from './ui.js';

const open = new Map(); // platform → kontrol

/**
 * @param {{id:string, platform:string, title?:string, prompt?:{type:string,message:string}, status?:string}} job
 * @param {{onAnswer?: (value:boolean)=>Promise<void>, subscribe?: (fn:(jobs:object[])=>void)=>Function}} opts
 */
export function openRemoteControl(job, opts = {}) {
  // İşin tarayıcı profili: ilan verme hesabın profilinde ("letgo"), tarama ise hesaptan
  // ayrı, girişsiz profilde ("letgo-tarama") yürür; kontrol doğru pencereye bağlanmalı.
  const platform = job && (job.browser || job.platform);
  if (!platform) {
    toast.error('Bu iş bir tarayıcıya bağlı değil.');
    return null;
  }
  if (open.has(platform)) return open.get(platform);

  let zoom = false;
  let stopped = false;
  let frameTimer = null;
  let stateTimer = null;
  let objectUrl = null;
  let lastFrameAt = 0;
  let current = job;
  let sending = 0;

  const sheet = openSheet({
    title: 'Tarayıcıyı buradan kontrol et',
    subtitle: `${platformName(job.platform || platform)}${job.browser && job.browser !== job.platform ? ' (tarama tarayıcısı)' : ''} · ${job.title || ''}`,
    icon: 'phone',
    size: 'remote',
    className: 'remote-sheet',
    body: html`
      <div class="rc">
        <div class="rc-prompt" data-prompt></div>
        <div class="rc-meta">
          <span class="rc-live" data-live><i aria-hidden="true"></i><span>Bağlanıyor…</span></span>
          <span class="rc-page" data-page></span>
          <button type="button" class="btn btn-ghost btn-sm rc-zoom" data-zoom aria-pressed="false">${icon('zoomIn', { size: 16 })}<span>Yakınlaştır</span></button>
        </div>
        <div class="rc-viewport" data-viewport>
          <div class="rc-screen" data-screen>
            <img class="rc-img" alt="Tarayıcı ekranı. Dokunduğunuz yere tıklanır." draggable="false" hidden />
            <div class="rc-wait" data-wait>${icon('browser', { size: 28 })}<span>Ekran görüntüsü bekleniyor…</span></div>
            <div class="rc-idle" data-idle hidden>
              ${icon('checkCircle', { size: 26 })}
              <strong>Tarayıcı artık sizi beklemiyor</strong>
              <span>İşlem devam ediyor ya da tamamlandı. Bu pencereyi kapatabilirsiniz.</span>
            </div>
          </div>
        </div>
        <p class="rc-tip">${icon('pointer', { size: 15 })}<span>Ekrana dokunduğunuz nokta tarayıcıda tıklanır.</span></p>
      </div>`,
    footer: html`
      <form class="rc-type" data-type-form autocomplete="off">
        <label class="sr-only" for="rc-text">Tarayıcıya yazılacak metin</label>
        <input id="rc-text" class="input" type="text" placeholder="Yazılacak metin (ör. SMS kodu)" autocomplete="off" autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="send" maxlength="500" />
        <button type="submit" class="btn btn-primary">${icon('keyboard', { size: 18 })}<span>Yaz</span></button>
      </form>
      <div class="rc-keys" role="group" aria-label="Tuşlar ve kaydırma">
        <button type="button" class="btn btn-sm" data-key="Enter" aria-label="Enter tuşu">${icon('enter', { size: 16 })}<span>Enter</span></button>
        <button type="button" class="btn btn-sm" data-key="Backspace" aria-label="Geri silme tuşu">${icon('backspace', { size: 16 })}</button>
        <button type="button" class="btn btn-sm" data-key="Tab" aria-label="Tab tuşu">Tab</button>
        <button type="button" class="btn btn-sm" data-key="Escape" aria-label="Escape tuşu">Esc</button>
        <button type="button" class="btn btn-sm" data-scroll="-500" aria-label="Yukarı kaydır">${icon('arrowUp', { size: 16 })}</button>
        <button type="button" class="btn btn-sm" data-scroll="500" aria-label="Aşağı kaydır">${icon('arrowDown', { size: 16 })}</button>
      </div>
      <p class="rc-hint">${icon('lock', { size: 14 })}<span>Yazdıklarınız yalnızca AutoSell'in çalıştığı bilgisayardaki tarayıcıya gönderilir, hiçbir yerde saklanmaz.</span></p>
      <p class="rc-note" data-note role="status" hidden></p>`,
    onClose() {
      stop();
      open.delete(platform);
    },
  });

  const root = sheet.root;
  const img = $('.rc-img', root);
  const waitEl = $('[data-wait]', root);
  const idleEl = $('[data-idle]', root);
  const liveEl = $('[data-live]', root);
  const pageEl = $('[data-page]', root);
  const noteEl = $('[data-note]', root);
  const screen = $('[data-screen]', root);
  const viewport = $('[data-viewport]', root);
  const input = $('#rc-text', root);

  const note = (text, tone = 'warning') => {
    noteEl.textContent = text;
    noteEl.dataset.tone = tone;
    noteEl.hidden = !text;
    clearTimeout(note.t);
    if (text) note.t = setTimeout(() => (noteEl.hidden = true), 4000);
  };

  const renderPrompt = () => {
    const box = $('[data-prompt]', root);
    const p = current && current.prompt;
    if (!p) {
      box.innerHTML = '';
      return;
    }
    box.innerHTML = html`
      <div class="rc-prompt-box">
        ${icon(p.type === 'confirm' ? 'bell' : 'hand', { size: 18 })}
        <p>${p.message}</p>
        ${p.type === 'confirm' && opts.onAnswer ? html`
          <div class="rc-prompt-actions">
            <button type="button" class="btn btn-sm" data-answer="no">Hayır</button>
            <button type="button" class="btn btn-sm btn-primary" data-answer="yes">${icon('check', { size: 16 })}<span>Evet, yayınla</span></button>
          </div>` : ''}
      </div>`.s;
  };

  const setIdle = (idle) => {
    idleEl.hidden = !idle;
    screen.classList.toggle('is-idle', idle);
    $$('.rc-keys button, .rc-type button, .rc-type input', root).forEach((b) => (b.disabled = idle));
    if (idle) {
      liveEl.classList.remove('is-live');
      $('span', liveEl).textContent = 'Bekleme bitti';
    }
  };

  const updateLive = () => {
    const age = lastFrameAt ? (Date.now() - lastFrameAt) / 1000 : Infinity;
    const live = age < 4;
    liveEl.classList.toggle('is-live', live);
    $('span', liveEl).textContent = live ? 'Canlı' : lastFrameAt ? 'Bağlantı yavaş…' : 'Bağlanıyor…';
  };

  async function pollFrame() {
    if (stopped) return;
    try {
      const res = await fetch(`/api/browser/${enc(platform)}/screen?t=${Date.now()}`, { cache: 'no-store', credentials: 'same-origin' });
      if (res.status === 200) {
        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        await new Promise((resolve) => {
          const pre = new Image();
          pre.onload = pre.onerror = resolve;
          pre.src = url;
        });
        if (stopped) {
          URL.revokeObjectURL(url);
          return;
        }
        img.src = url;
        img.hidden = false;
        waitEl.hidden = true;
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = url;
        lastFrameAt = Date.now();
      } else if (res.status === 401) {
        stop();
        return;
      }
    } catch {
      /* ağ hatası: bir sonraki turda yeniden dene */
    }
    updateLive();
    if (!stopped) frameTimer = setTimeout(pollFrame, document.hidden ? 3000 : 700);
  }

  async function pollState() {
    if (stopped) return;
    try {
      const s = await api(`/api/browser/${enc(platform)}/state`);
      const title = s.title || '';
      const url = safeUrl(s.url) || s.url || '';
      pageEl.innerHTML = html`${title ? html`<strong>${title}</strong>` : ''}${url ? html`<span>${url}</span>` : ''}`.s;
      pageEl.title = url;
      if (!s.active) setIdle(true);
      else setIdle(false);
    } catch {
      /* yok say */
    }
    if (!stopped) stateTimer = setTimeout(pollState, 1500);
  }

  function stop() {
    stopped = true;
    clearTimeout(frameTimer);
    clearTimeout(stateTimer);
    if (unsubscribe) unsubscribe();
    if (objectUrl) {
      const u = objectUrl;
      setTimeout(() => URL.revokeObjectURL(u), 1000);
      objectUrl = null;
    }
  }

  async function send(command, btn) {
    sending++;
    screen.classList.add('is-sending');
    try {
      await api.post(`/api/browser/${enc(platform)}/input`, command);
      clearTimeout(frameTimer);
      frameTimer = setTimeout(pollFrame, 350);
      return true;
    } catch (e) {
      if (e.status === 409) {
        note('Tarayıcı şu an kullanıcı girişi beklemiyor.');
        setIdle(true);
      } else note(e.message || 'Komut gönderilemedi.', 'danger');
      return false;
    } finally {
      sending--;
      if (!sending) screen.classList.remove('is-sending');
      if (btn) btn.blur();
    }
  }

  function ripple(x, y) {
    const r = document.createElement('span');
    r.className = 'rc-ripple';
    r.style.left = `${x}px`;
    r.style.top = `${y}px`;
    screen.appendChild(r);
    setTimeout(() => r.remove(), 650);
  }

  img.addEventListener('click', (e) => {
    if (screen.classList.contains('is-idle')) return;
    const rect = img.getBoundingClientRect();
    if (!rect.width || !rect.height) return;
    const x = Math.min(1, Math.max(0, (e.clientX - rect.left) / rect.width));
    const y = Math.min(1, Math.max(0, (e.clientY - rect.top) / rect.height));
    const srect = screen.getBoundingClientRect();
    ripple(e.clientX - srect.left, e.clientY - srect.top);
    send({ type: 'click', x: Number(x.toFixed(4)), y: Number(y.toFixed(4)) });
  });

  $('[data-type-form]', root).addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = input.value;
    if (!text) {
      input.focus();
      return;
    }
    const btn = $('button[type="submit"]', e.currentTarget);
    setBusy(btn, true, 'Yazılıyor…');
    const ok = await send({ type: 'type', text });
    setBusy(btn, false);
    if (ok) {
      input.value = '';
      note('Metin gönderildi.', 'success');
    }
  });

  sheet.foot.addEventListener('click', (e) => {
    const k = e.target.closest('[data-key]');
    if (k) send({ type: 'key', key: k.dataset.key }, k);
    const s = e.target.closest('[data-scroll]');
    if (s) send({ type: 'scroll', dy: Number(s.dataset.scroll) }, s);
  });

  $('[data-zoom]', root).addEventListener('click', (e) => {
    zoom = !zoom;
    const b = e.currentTarget;
    b.setAttribute('aria-pressed', String(zoom));
    b.innerHTML = html`${icon(zoom ? 'zoomOut' : 'zoomIn', { size: 16 })}<span>${zoom ? 'Sığdır' : 'Yakınlaştır'}</span>`.s;
    viewport.classList.toggle('is-zoomed', zoom);
  });

  root.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-answer]');
    if (!a || !opts.onAnswer) return;
    $$('[data-answer]', root).forEach((b) => (b.disabled = true));
    try {
      await opts.onAnswer(a.dataset.answer === 'yes');
      sheet.close('answered');
    } catch (err) {
      toast.error(err.message || 'Yanıt gönderilemedi.');
      $$('[data-answer]', root).forEach((b) => (b.disabled = false));
    }
  });

  let unsubscribe = null;
  if (opts.subscribe) {
    unsubscribe = opts.subscribe((jobs) => {
      const j = jobs.find((x) => x.id === job.id);
      if (!j || j.status !== 'waiting') {
        current = j || { ...current, prompt: null };
        renderPrompt();
        setIdle(true);
        return;
      }
      const changed = JSON.stringify(j.prompt) !== JSON.stringify(current && current.prompt);
      current = j;
      if (changed) renderPrompt();
    });
  }

  renderPrompt();
  pollFrame();
  pollState();
  const ctrl = { sheet, close: () => sheet.close() };
  open.set(platform, ctrl);
  return ctrl;
}
