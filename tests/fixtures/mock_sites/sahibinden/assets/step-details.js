/* sahibinden.com mock - posting step 2: "İlan Detayları" form */
(function (w, d) {
  'use strict';
  var S = w.SHB, D = w.SHB_DATA;
  if (!S.requireLogin()) { return; }

  var draft = S.getDraft();
  if (!draft.category_path || !D.isLeafPath(draft.category_path)) {
    w.location.replace('ilan-ver.html');
    return;
  }

  var REQ = 'Bu alan zorunludur.';
  var MAX_PHOTOS = 20;
  var path = draft.category_path;
  var group = D.attrGroup(path);
  var attrs = D.ATTRS[group];

  var form = d.getElementById('classifiedPostForm');
  var alertBox = d.getElementById('formAlert');
  var titleInput = d.getElementById('addClassifiedTitle');
  var titleCount = d.getElementById('titleCharCount');
  var editor = d.getElementById('descriptionEditor');
  var descInput = d.getElementById('descriptionInput');
  var priceInput = d.getElementById('addClassifiedPrice');
  var currency = d.getElementById('currencySelect');
  var attrBox = d.getElementById('attributeFields');
  var city = d.getElementById('addressCity');
  var town = d.getElementById('addressTown');
  var quarter = d.getElementById('addressQuarter');
  var terms = d.getElementById('rulesAccepted');
  var fileInput = d.getElementById('photoUploadInput');
  var photoList = d.getElementById('photoList');
  var photoStatus = d.getElementById('photoStatus');
  var photoError = d.getElementById('photoError');

  d.getElementById('selectedCategoryPath').textContent = path.join(' > ');

  /* ---------------- helpers ---------------- */
  function rowOf(el) { return el.closest('.form-row'); }
  function setError(row, msg) {
    row.classList.add('has-error');
    var e = row.querySelector('.field-error');
    e.textContent = msg;
    e.hidden = false;
  }
  function clearError(row) {
    if (!row) { return; }
    row.classList.remove('has-error');
    var e = row.querySelector('.field-error');
    if (e) { e.hidden = true; e.textContent = ''; }
  }
  function fillSelect(sel, placeholder, list) {
    sel.innerHTML = '';
    var o = d.createElement('option');
    o.value = '';
    o.textContent = placeholder;
    sel.appendChild(o);
    list.forEach(function (v) {
      var op = d.createElement('option');
      op.value = v;
      op.textContent = v;
      sel.appendChild(op);
    });
  }

  /* ---------------- attributes ---------------- */
  function buildAttributes() {
    var html = '';
    D.fixedInfo(path).forEach(function (r) {
      html += '<div class="form-row readonly"><div class="form-label">' + S.escapeHtml(r[0]) + '</div>' +
        '<div class="form-field"><div class="readonly-value">' + S.escapeHtml(r[1]) + '</div></div></div>';
    });
    attrs.forEach(function (a) {
      var id = 'attr_' + a.key;
      var star = a.required ? ' <span class="req">*</span>' : '';
      var labelHtml = (a.type !== 'radio' && a.labelFor)
        ? '<label class="form-label" for="' + id + '">' + S.escapeHtml(a.label) + star + '</label>'
        : '<div class="form-label">' + S.escapeHtml(a.label) + star + '</div>';
      var field = '';
      if (a.type === 'select') {
        field = '<select id="' + id + '" name="' + id + '"><option value="">Seçiniz</option>' +
          a.options.map(function (o) { return '<option value="' + S.escapeHtml(o) + '">' + S.escapeHtml(o) + '</option>'; }).join('') +
          '</select>';
      } else if (a.type === 'text') {
        field = '<input type="text" id="' + id + '" name="' + id + '" autocomplete="off"' + (a.numeric ? ' inputmode="numeric"' : '') + '>';
      } else {
        field = '<div class="radio-group">' + a.options.map(function (o) {
          return '<label><input type="radio" name="' + id + '" value="' + S.escapeHtml(o) + '"> ' + S.escapeHtml(o) + '</label>';
        }).join('') + '</div>';
      }
      html += '<div class="form-row" id="row-' + id + '">' + labelHtml +
        '<div class="form-field">' + field + '<div class="field-error" hidden></div></div></div>';
    });
    attrBox.innerHTML = html;
    attrBox.addEventListener('change', function (e) { clearError(rowOf(e.target)); });
    attrBox.addEventListener('input', function (e) {
      var t = e.target;
      if (t.type === 'text' && t.inputMode === 'numeric') {
        var dg = S.digits(t.value);
        if (dg !== t.value) { t.value = dg; }
      }
      clearError(rowOf(t));
    });
  }

  function getAttr(a) {
    var id = 'attr_' + a.key;
    if (a.type === 'radio') {
      var r = form.querySelector('input[name="' + id + '"]:checked');
      return r ? r.value : '';
    }
    var el = d.getElementById(id);
    return el ? el.value.trim() : '';
  }
  function setAttr(a, v) {
    var id = 'attr_' + a.key;
    if (a.type === 'radio') {
      form.querySelectorAll('input[name="' + id + '"]').forEach(function (r) { r.checked = (r.value === v); });
    } else {
      var el = d.getElementById(id);
      if (el) { el.value = v; }
    }
  }

  /* ---------------- title / description / price ---------------- */
  function updateTitleCount() { titleCount.textContent = String(titleInput.value.length); }
  titleInput.addEventListener('input', function () { updateTitleCount(); clearError(rowOf(titleInput)); });

  function plainDescription() {
    var t = (editor.innerText || '').replace(/ /g, ' ');
    t = t.replace(/[ \t]+\n/g, '\n').replace(/\n{3,}/g, '\n\n');
    return t.trim();
  }
  function syncDescription() { descInput.value = editor.innerHTML; }
  editor.addEventListener('input', function () { syncDescription(); clearError(rowOf(editor)); });
  editor.addEventListener('paste', function (e) {
    var text = (e.clipboardData || w.clipboardData).getData('text/plain');
    e.preventDefault();
    d.execCommand('insertText', false, text);
  });
  d.querySelectorAll('.editor-toolbar button').forEach(function (b) {
    b.addEventListener('mousedown', function (e) { e.preventDefault(); });
    b.addEventListener('click', function () {
      editor.focus();
      d.execCommand(b.getAttribute('data-cmd'), false, null);
      syncDescription();
    });
  });

  priceInput.addEventListener('input', function () {
    var dg = S.digits(priceInput.value).replace(/^0+(?=\d)/, '').slice(0, 12);
    var formatted = dg ? S.formatNumber(dg) : '';
    if (priceInput.value !== formatted) { priceInput.value = formatted; }
    clearError(rowOf(priceInput));
  });

  /* ---------------- address (dependent dropdowns) ---------------- */
  var townToken = 0, quarterToken = 0;
  fillSelect(city, 'Seçiniz', D.CITIES);

  function loadTowns(cityName, done) {
    var my = ++townToken;
    quarterToken++;
    fillSelect(quarter, 'Önce ilçe seçiniz', []);
    quarter.disabled = true;
    town.disabled = true;
    if (!cityName) { fillSelect(town, 'Önce il seçiniz', []); return; }
    fillSelect(town, 'Yükleniyor...', []);
    w.setTimeout(function () {
      if (my !== townToken) { return; }
      fillSelect(town, 'Seçiniz', D.districtsOf(cityName));
      town.disabled = false;
      if (done) { done(); }
    }, 350);
  }
  function loadQuarters(cityName, townName, done) {
    var my = ++quarterToken;
    quarter.disabled = true;
    if (!townName) { fillSelect(quarter, 'Önce ilçe seçiniz', []); return; }
    fillSelect(quarter, 'Yükleniyor...', []);
    w.setTimeout(function () {
      if (my !== quarterToken) { return; }
      fillSelect(quarter, 'Seçiniz', D.quartersOf(cityName, townName));
      quarter.disabled = false;
      if (done) { done(); }
    }, 300);
  }
  city.addEventListener('change', function () { clearError(rowOf(city)); loadTowns(city.value); });
  town.addEventListener('change', function () { clearError(rowOf(town)); loadQuarters(city.value, town.value); });
  quarter.addEventListener('change', function () { clearError(rowOf(quarter)); });
  terms.addEventListener('change', function () { clearError(rowOf(terms)); });

  /* ---------------- photos ---------------- */
  var photos = [];
  var photoNote = '';

  function isImage(f) {
    return (f.type && f.type.indexOf('image/') === 0) || /\.(jpe?g|png|gif|webp|bmp|heic|svg)$/i.test(f.name);
  }
  function uploadingCount() { return photos.filter(function (p) { return p.status === 'uploading'; }).length; }

  function renderPhotos() {
    photoList.innerHTML = '';
    photos.forEach(function (p, idx) {
      var li = d.createElement('li');
      li.className = 'photo-item' + (p.status === 'uploading' ? ' uploading' : '');
      var thumb = p.url ? '<img src="' + p.url + '" alt="">' : '<span>Foto</span>';
      li.innerHTML = '<div class="thumb">' + thumb + '</div>' +
        '<span class="name">' + S.escapeHtml(p.name) + '</span>' +
        '<span class="state">' + (p.status === 'uploading' ? 'Yükleniyor...' : 'Yüklendi') + '</span>' +
        '<a href="#" class="remove">Kaldır</a>';
      var img = li.querySelector('img');
      if (img) { img.addEventListener('error', function () { img.replaceWith(d.createTextNode('Foto')); }); }
      li.querySelector('.remove').addEventListener('click', function (e) {
        e.preventDefault();
        photos.splice(idx, 1);
        photoNote = '';
        renderPhotos();
      });
      photoList.appendChild(li);
    });
    var up = uploadingCount();
    photoStatus.classList.toggle('done', photos.length > 0 && up === 0);
    if (!photos.length) {
      photoStatus.textContent = 'Henüz fotoğraf eklenmedi.';
    } else if (up) {
      photoStatus.textContent = 'Fotoğraflar yükleniyor... (' + (photos.length - up) + '/' + photos.length + ')';
    } else {
      photoStatus.textContent = photos.length + ' fotoğraf yüklendi';
    }
    if (photoNote) { photoStatus.textContent += ' – ' + photoNote; }
    if (!up) { photoError.hidden = true; }
  }

  d.getElementById('btnAddPhoto').addEventListener('click', function () { fileInput.click(); });
  fileInput.addEventListener('change', function () {
    var files = Array.prototype.slice.call(fileInput.files || []);
    fileInput.value = '';
    photoNote = '';
    var added = 0;
    files.forEach(function (f) {
      if (photos.length >= MAX_PHOTOS) { photoNote = 'En fazla ' + MAX_PHOTOS + ' fotoğraf ekleyebilirsiniz.'; return; }
      if (!isImage(f)) { photoNote = 'Desteklenmeyen dosya: ' + f.name; return; }
      var p = { name: f.name, status: 'uploading', url: null };
      try { p.url = URL.createObjectURL(f); } catch (e) { p.url = null; }
      photos.push(p);
      w.setTimeout(function () { p.status = 'done'; renderPhotos(); }, 300 + 120 * added);
      added++;
    });
    renderPhotos();
  });

  /* ---------------- restore previous values (coming back from preview) ---------------- */
  buildAttributes();
  if (draft.title) { titleInput.value = draft.title; }
  updateTitleCount();
  if (draft.description_html) { editor.innerHTML = S.sanitizeHtml(draft.description_html); syncDescription(); }
  if (draft.price) { priceInput.value = S.formatNumber(draft.price); }
  if (draft.currency) { currency.value = draft.currency; }
  if (draft.attributes) {
    attrs.forEach(function (a) { if (draft.attributes[a.label]) { setAttr(a, draft.attributes[a.label]); } });
  }
  if (draft.photos && draft.photos.length) {
    photos = draft.photos.map(function (n) { return { name: n, status: 'done', url: null }; });
  }
  renderPhotos();
  if (draft.terms_accepted) { terms.checked = true; }
  if (draft.address && draft.address.il) {
    var addr = draft.address;
    city.value = addr.il;
    loadTowns(addr.il, function () {
      town.value = addr.ilce || '';
      if (town.value) {
        loadQuarters(addr.il, addr.ilce, function () { quarter.value = addr.mahalle || ''; });
      }
    });
  }

  /* ---------------- submit ---------------- */
  form.addEventListener('submit', function (e) {
    e.preventDefault();
    syncDescription();
    form.querySelectorAll('.form-row.has-error').forEach(clearError);
    alertBox.hidden = true;
    photoError.hidden = true;
    var missing = false;

    if (!titleInput.value.trim()) { setError(rowOf(titleInput), REQ); missing = true; }
    var desc = plainDescription();
    if (!desc) { setError(rowOf(editor), REQ); missing = true; }
    else if (desc.replace(/\s+/g, ' ').length < 20) { setError(rowOf(editor), 'Açıklama en az 20 karakter olmalıdır.'); missing = true; }
    var priceDigits = S.digits(priceInput.value);
    if (!priceDigits || Number(priceDigits) <= 0) { setError(rowOf(priceInput), REQ); missing = true; }
    var attrValues = {};
    attrs.forEach(function (a) {
      var v = getAttr(a);
      if (v) { attrValues[a.label] = v; }
      else if (a.required) { setError(d.getElementById('row-attr_' + a.key), REQ); missing = true; }
    });
    [city, town, quarter].forEach(function (sel) {
      if (!sel.value) { setError(rowOf(sel), REQ); missing = true; }
    });
    if (!terms.checked) { setError(rowOf(terms), REQ); missing = true; }
    var pending = uploadingCount() > 0;
    if (pending) {
      photoError.textContent = 'Fotoğraf yükleme işlemi devam ediyor, lütfen bekleyin.';
      photoError.hidden = false;
    }

    if (missing || pending) {
      alertBox.textContent = missing ? 'Lütfen zorunlu alanları doldurun.' : 'Fotoğraf yükleme işlemi devam ediyor, lütfen bekleyin.';
      alertBox.hidden = false;
      alertBox.scrollIntoView({ block: 'start' });
      return;
    }

    var fresh = S.getDraft();
    fresh.category_path = path.slice();
    fresh.title = titleInput.value.trim();
    fresh.description = desc;
    fresh.description_html = S.sanitizeHtml(editor.innerHTML);
    fresh.price = Number(priceDigits);
    fresh.currency = currency.value;
    fresh.attributes = attrValues;
    fresh.address = { il: city.value, ilce: town.value, mahalle: quarter.value };
    fresh.photos = photos.map(function (p) { return p.name; });
    fresh.terms_accepted = true;
    fresh.details_completed = true;
    fresh.previewed = false;
    S.saveDraft(fresh);
    S.showOverlay('Kaydediliyor...');
    w.setTimeout(function () { w.location.href = 'ilan-ver-onizleme.html'; }, 300);
  });
})(window, document);
