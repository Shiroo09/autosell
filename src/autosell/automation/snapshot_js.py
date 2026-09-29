"""Sayfadaki etkileşimli öğeleri (form alanları ve tıklanabilirler) çıkaran JS.

Her öğeye kalıcı bir ``data-as-id`` verilir; eylemler bu kimlikle yapılır.
Etiketler; <label>, aria-* öznitelikleri, "tek alan içeren en yakın satır
kapsayıcısının görünür metni" ve "önceki kardeş öğenin metni" sezgileriyle
bulunur. Böylece sitenin CSS sınıflarını bilmeden de çalışır.
"""

SNAPSHOT_JS = r"""
(opts) => {
  opts = opts || {};
  const MAX_CLICKABLES = opts.maxClickables || 500;
  const clean = (s) => (s || '').replace(/[\s ]+/g, ' ').trim();
  const cut = (s, n) => { s = clean(s); return s.length > n ? s.slice(0, n) : s; };
  if (typeof window.__asCounter !== 'number') window.__asCounter = 0;
  const idOf = (el) => {
    let id = el.getAttribute('data-as-id');
    if (!id) { window.__asCounter += 1; id = 'e' + window.__asCounter; el.setAttribute('data-as-id', id); }
    return id;
  };
  const isVisible = (el) => {
    if (!el || !el.getClientRects || el.getClientRects().length === 0) return false;
    const st = getComputedStyle(el);
    if (st.visibility === 'hidden' || st.display === 'none') return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;
  };
  const inChrome = (el) => !!el.closest('header, nav, footer, [role=banner], [role=navigation], [role=contentinfo]');
  const CONTROL_SEL = 'input:not([type=hidden]), select, textarea, [contenteditable=""], [contenteditable=true], [role=combobox], [aria-haspopup=listbox]';
  const FIELD_SEL = CONTROL_SEL + ', [role=radiogroup], [role=switch]';
  const SKIP_TEXT_SEL = 'script, style, noscript, select, option, textarea, input, button, [role=listbox], [role=option], [role=combobox], [aria-haspopup=listbox], [contenteditable=""], [contenteditable=true], [data-as-skip]';
  const ERROR_SEL = '[role=alert], .error, .errors, .invalid-feedback, .field-error, .error-message, [class*="error" i], [class*="invalid" i], [class*="hata" i]';

  // Görünür metin (form kontrolleri, gizli öğeler ve açılır listeler hariç)
  const visibleText = (root, skipErrors) => {
    const parts = [];
    const walk = (node) => {
      if (node.nodeType === 3) { parts.push(node.nodeValue); return; }
      if (node.nodeType !== 1) return;
      if (node.matches(SKIP_TEXT_SEL)) return;
      if (skipErrors && node !== root && node.matches(ERROR_SEL) && !node.querySelector(CONTROL_SEL)) return;
      const st = getComputedStyle(node);
      if (st.display === 'none' || st.visibility === 'hidden') return;
      for (const c of node.childNodes) walk(c);
    };
    walk(root);
    return clean(parts.join(' '));
  };

  const otherControls = (node, own) => Array.from(node.querySelectorAll(CONTROL_SEL))
    .filter(x => !own.includes(x) && (isVisible(x) || (x.type === 'file')));

  // Yalnız bu alanı (ya da grubu) içeren en yakın metinli kapsayıcı = satır
  const rowOf = (el, own) => {
    own = own || [el];
    let node = el.parentElement, best = null;
    for (let depth = 0; node && depth < 6 && node !== document.body; depth++, node = node.parentElement) {
      if (otherControls(node, own).length > 0) break;
      best = node;
      if (visibleText(node, true).length > 0) {
        const up = node.parentElement;
        if (up && up !== document.body && otherControls(up, own).length === 0 && visibleText(up, true).length <= 80) best = up;
        break;
      }
    }
    return best;
  };

  const errorIn = (row) => {
    if (!row) return '';
    return Array.from(row.querySelectorAll(ERROR_SEL)).filter(e => isVisible(e) && !e.querySelector(CONTROL_SEL))
      .map(e => clean(e.innerText)).filter(t => t && t.length < 200).join(' | ');
  };

  const precedingText = (el) => {
    let node = el;
    for (let depth = 0; node && depth < 3; depth++, node = node.parentElement) {
      let sib = node.previousElementSibling;
      for (let i = 0; sib && i < 3; i++, sib = sib.previousElementSibling) {
        if (sib.matches(CONTROL_SEL) || sib.querySelector(CONTROL_SEL)) break;
        const t = visibleText(sib, true);
        if (t && t.length <= 60) return t;
      }
    }
    return '';
  };

  const ariaLabel = (el) => {
    if (!el) return '';
    const lb = el.getAttribute('aria-labelledby');
    if (lb) {
      const t = lb.split(/\s+/).map(i => document.getElementById(i)).filter(Boolean)
        .map(n => clean(n.innerText || n.textContent)).join(' ');
      if (t) return t;
    }
    return clean(el.getAttribute('aria-label') || '');
  };

  const explicitLabel = (el) => {
    const a = ariaLabel(el);
    if (a) return a;
    if (el.labels && el.labels.length) {
      const t = Array.from(el.labels).map(l => visibleText(l, true)).filter(Boolean).join(' ');
      if (t) return t;
    }
    if (el.id) {
      const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
      if (l && visibleText(l, true)) return visibleText(l, true);
    }
    return '';
  };

  const fields = [];
  const seenGroups = new Set();
  for (const el of Array.from(document.querySelectorAll(FIELD_SEL))) {
    const tag = el.tagName.toLowerCase();
    const type = (el.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && ['submit', 'button', 'reset', 'image'].includes(type)) continue;
    if (el.closest('[data-as-skip]')) continue;
    const role = (el.getAttribute('role') || '').toLowerCase();
    const isFile = tag === 'input' && type === 'file';
    const vis = isVisible(el);
    let visibleProxy = vis;
    if (!vis && tag === 'input' && (type === 'radio' || type === 'checkbox')) {
      const lab = (el.labels && el.labels[0]) || el.closest('label');
      visibleProxy = !!(lab && isVisible(lab));
    }
    if (!visibleProxy && !isFile) continue;

    const f = {
      id: idOf(el), tag, type, role, kind: '',
      name: el.getAttribute('name') || '',
      placeholder: clean(el.getAttribute('placeholder') || ''),
      required: !!(el.required || el.getAttribute('aria-required') === 'true'),
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true'),
      in_chrome: inChrome(el), hidden: !vis,
      maxlength: el.maxLength && el.maxLength > 0 ? el.maxLength : null,
      autocomplete: el.getAttribute('autocomplete') || '',
      options: [], value: '', checked: false, label: '', error: '', option_text: '',
      multiple: !!el.multiple, accept: el.getAttribute('accept') || '',
    };

    if (tag === 'input' && type === 'radio') {
      const key = 'r:' + (el.name || f.id);
      if (seenGroups.has(key)) continue;
      seenGroups.add(key);
      const group = el.name ? Array.from(document.querySelectorAll('input[type=radio][name="' + CSS.escape(el.name) + '"]')) : [el];
      const row = rowOf(el, group);
      f.kind = 'radio';
      f.options = group.map(r => {
        const lab = (r.labels && r.labels[0]) || r.closest('label');
        const target = lab && isVisible(lab) ? lab : r;
        return { id: idOf(target), input_id: idOf(r), value: r.value, text: cut(lab ? visibleText(lab, true) : r.value, 80) || r.value, selected: r.checked };
      });
      f.value = (f.options.find(o => o.selected) || {}).text || '';
      f.required = group.some(r => r.required || r.getAttribute('aria-required') === 'true');
      f.error = errorIn(row);
      const fs = el.closest('fieldset');
      const legend = fs ? fs.querySelector('legend') : null;
      let label = ariaLabel(el.closest('[role=radiogroup]')) || (legend ? clean(legend.innerText) : '') || (row ? visibleText(row, true) : '') || precedingText(el);
      for (const o of f.options) if (o.text) label = clean(label.split(o.text).join(' '));
      f.label = cut(label, 80);
      fields.push(f);
      continue;
    }

    if (role === 'radiogroup') {
      if (el.querySelector('input[type=radio]')) continue;
      const opts = Array.from(el.querySelectorAll('[role=radio], button, [role=option]')).filter(isVisible);
      if (!opts.length) continue;
      const row = rowOf(el, [el]);
      f.kind = 'radio';
      f.options = opts.map(o => ({
        id: idOf(o), value: o.getAttribute('data-value') || '', text: cut(o.innerText || o.getAttribute('aria-label'), 80),
        selected: o.getAttribute('aria-checked') === 'true' || o.getAttribute('aria-selected') === 'true' || /\b(selected|active|checked)\b/i.test(typeof o.className === 'string' ? o.className : ''),
      }));
      f.value = (f.options.find(o => o.selected) || {}).text || '';
      f.required = f.required || el.getAttribute('aria-required') === 'true';
      f.error = errorIn(row);
      f.label = cut(ariaLabel(el) || (row ? visibleText(row, true) : '') || precedingText(el), 80);
      fields.push(f);
      continue;
    }

    if (tag === 'select') {
      f.kind = 'select';
      f.options = Array.from(el.options).map(o => ({ value: o.value, text: cut(o.text, 100), selected: o.selected, disabled: o.disabled }));
      const sel = el.options[el.selectedIndex];
      f.value = sel ? clean(sel.text) : '';
      f.selected_value = sel ? sel.value : '';
    } else if (tag === 'textarea') {
      f.kind = 'textarea';
      f.value = el.value || '';
    } else if (tag === 'input' && type === 'checkbox') {
      f.kind = 'checkbox';
      f.checked = el.checked;
      const lab = (el.labels && el.labels[0]) || el.closest('label');
      f.option_text = lab ? cut(visibleText(lab, true), 160) : '';
    } else if (role === 'switch') {
      f.kind = 'checkbox';
      f.checked = el.getAttribute('aria-checked') === 'true';
    } else if (isFile) {
      f.kind = 'file';
    } else if (role === 'combobox' || el.getAttribute('aria-haspopup') === 'listbox') {
      if (tag === 'input') { f.kind = 'autocomplete'; f.value = el.value || ''; }
      else { f.kind = 'combobox'; f.value = cut(el.innerText, 80); }
    } else if (el.isContentEditable) {
      if (el.parentElement && el.parentElement.isContentEditable) continue;
      f.kind = 'richtext';
      f.value = cut(el.innerText, 5000);
    } else if (tag === 'input') {
      f.kind = ['number', 'tel', 'email', 'password', 'date', 'search', 'url'].includes(type) ? type : 'text';
      f.value = el.value || '';
      if (f.kind === 'text' && (el.getAttribute('aria-autocomplete') || el.getAttribute('list'))) f.kind = 'autocomplete';
    } else {
      continue;
    }
    const row = rowOf(el, [el]);
    f.error = errorIn(row);
    f.label = cut(explicitLabel(el) || (row ? visibleText(row, true) : '') || precedingText(el) || f.placeholder || f.name, 80);
    if (f.kind === 'checkbox' && !f.option_text) f.option_text = f.label;
    fields.push(f);
  }

  // ---------------------------------------------------------------- tıklanabilirler
  const CLICK_SEL = 'a[href], button, [role=button], [role=link], [role=tab], [role=menuitem], [role=option], [role=treeitem], [role=radio], input[type=submit], input[type=button], li, [onclick], [tabindex]:not([tabindex="-1"])';
  const candidates = Array.from(document.querySelectorAll(CLICK_SEL));
  let scanned = 0;
  for (const el of document.querySelectorAll('div, span, label, p, h2, h3, h4, strong')) {
    if (++scanned > 8000) break;
    if (getComputedStyle(el).cursor === 'pointer') candidates.push(el);
  }
  const clickables = [];
  const seen = new Set();
  const INNER_CLICK = 'a[href], button, [role=button], [role=option], [role=radio], input, select, textarea';
  for (const el of candidates) {
    if (clickables.length >= MAX_CLICKABLES) break;
    if (seen.has(el)) continue;
    seen.add(el);
    if (!isVisible(el) || el.closest('[data-as-skip]')) continue;
    const tag = el.tagName.toLowerCase();
    const generic = !['a', 'button', 'input'].includes(tag) && !el.getAttribute('role');
    if (generic) {
      const inner = el.querySelector(INNER_CLICK);
      if (inner && isVisible(inner)) continue;
      const parent = el.parentElement;
      if (tag !== 'li' && parent && !['BODY', 'HTML'].includes(parent.tagName) && getComputedStyle(parent).cursor === 'pointer'
          && clean(parent.innerText).length <= 80 && !parent.querySelector(INNER_CLICK)) continue;
    }
    let text = tag === 'input' ? (el.value || el.getAttribute('aria-label') || '') : (el.innerText || el.getAttribute('aria-label') || el.getAttribute('title') || '');
    text = cut(text, 120);
    if (!text) {
      const img = el.querySelector('img[alt]');
      if (img) text = cut(img.getAttribute('alt'), 80);
    }
    if (!text) continue;
    const r = el.getBoundingClientRect();
    const cls = typeof el.className === 'string' ? el.className : '';
    let fixed = false;
    for (let n = el, i = 0; n && i < 6; i++, n = n.parentElement) {
      const p = getComputedStyle(n).position;
      if (p === 'fixed' || p === 'sticky') { fixed = true; break; }
    }
    clickables.push({
      id: idOf(el), tag, role: (el.getAttribute('role') || '').toLowerCase(), text,
      href: tag === 'a' ? el.href : '',
      disabled: !!(el.disabled || el.getAttribute('aria-disabled') === 'true' || /\bdisabled\b/i.test(cls)),
      selected: el.getAttribute('aria-selected') === 'true' || el.getAttribute('aria-checked') === 'true' || /\b(selected|active|is-active|checked)\b/i.test(cls),
      in_chrome: inChrome(el), fixed,
      x: Math.round(r.left + window.scrollX), y: Math.round(r.top + window.scrollY),
    });
  }

  const alerts = Array.from(document.querySelectorAll('[role=alert], .alert, .error, .errors, [class*="error" i], [class*="uyari" i], [class*="warning" i]'))
    .filter(e => isVisible(e) && !e.querySelector(CONTROL_SEL) && clean(e.innerText).length <= 240)
    .map(e => cut(e.innerText, 200)).filter(Boolean);
  const frames = Array.from(document.querySelectorAll('iframe')).map(f => f.src || '').filter(Boolean).slice(0, 20);
  const bodyText = document.body ? clean(document.body.innerText) : '';
  return {
    url: location.href, title: document.title, fields, clickables,
    text: bodyText.slice(0, opts.maxText || 8000),
    alerts: Array.from(new Set(alerts)).slice(0, 20), frames,
  };
}
"""

COOKIE_BANNER_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim().toLocaleLowerCase('tr');
  const prefer = ['sadece gerekli', 'gerekli çerezler', 'tümünü reddet', 'reddet', 'kabul et', 'tümünü kabul et',
                  'kabul ediyorum', 'anladım', 'tamam', 'accept', 'accept all', 'got it'];
  const containers = Array.from(document.querySelectorAll('div, section, aside, footer, dialog')).filter(el => {
    const st = getComputedStyle(el);
    if (!(st.position === 'fixed' || st.position === 'sticky')) return false;
    if (st.display === 'none' || st.visibility === 'hidden') return false;
    const t = clean(el.innerText);
    return t.includes('çerez') || t.includes('cookie') || t.includes('kvkk');
  });
  for (const c of containers) {
    const buttons = Array.from(c.querySelectorAll('button, a, [role=button]'));
    for (const want of prefer) {
      const b = buttons.find(x => clean(x.innerText) === want) || buttons.find(x => clean(x.innerText).startsWith(want));
      if (b) { b.click(); return clean(b.innerText); }
    }
  }
  return null;
}
"""

VISIBLE_OPTIONS_JS = r"""
() => {
  const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
  if (typeof window.__asCounter !== 'number') window.__asCounter = 0;
  const idOf = (el) => { let id = el.getAttribute('data-as-id'); if (!id) { window.__asCounter += 1; id = 'e' + window.__asCounter; el.setAttribute('data-as-id', id); } return id; };
  const vis = (el) => { if (!el.getClientRects().length) return false; const s = getComputedStyle(el); if (s.visibility === 'hidden' || s.display === 'none') return false; const r = el.getBoundingClientRect(); return r.width > 1 && r.height > 1; };
  const sel = '[role=option], [role=listbox] li, [role=menu] [role=menuitem], ul[class*="suggest" i] li, ul[class*="autocomplete" i] li, ul[class*="dropdown" i] li';
  const seen = new Set();
  return Array.from(document.querySelectorAll(sel)).filter(vis)
    .filter(o => { if (seen.has(o)) return false; seen.add(o); return clean(o.innerText).length > 0 && !o.querySelector('[role=option]'); })
    .map(o => ({ id: idOf(o), text: clean(o.innerText).slice(0, 120) })).slice(0, 300);
}
"""
