/* sahibinden.com mock - posting flow pages after the details form:
   Önizleme, Doping, Ödeme, İlan Onayı, Tebrikler, İlanı Görüntüle */
(function (w, d) {
  'use strict';
  var S = w.SHB, D = w.SHB_DATA;
  var REQ = 'Bu alan zorunludur.';
  var LISTING_NO = '1098765432';
  var LISTING_DATE = '28 Eylül 2026';
  var page = d.body.id;

  function $(id) { return d.getElementById(id); }

  /* Redirects to the right step when the draft is not far enough. */
  function ensure(stage) {
    var draft = S.getDraft();
    var order = ['category', 'details', 'preview', 'doping'];
    var ok = {
      category: !!(draft.category_path && D.isLeafPath(draft.category_path)),
      details: !!draft.details_completed,
      preview: !!draft.previewed,
      doping: !!draft.doping_step_done
    };
    var target = { category: 'ilan-ver.html', details: 'ilan-ver-detay.html', preview: 'ilan-ver-onizleme.html', doping: 'ilan-ver-doping.html' };
    for (var i = 0; i < order.length; i++) {
      if (order[i] === stage) { break; }
      if (!ok[order[i]]) { w.location.replace(target[order[i]]); return null; }
    }
    return draft;
  }

  function descriptionHtml(data) {
    if (data.description_html) { return S.sanitizeHtml(data.description_html); }
    return S.escapeHtml(data.description || '').replace(/\n/g, '<br>');
  }

  function renderDetail(data, opts) {
    opts = opts || {};
    var photos = data.photos || [];
    var addr = data.address || {};
    var info = '';
    if (opts.listingNo) {
      info += '<li><strong>İlan No</strong>&nbsp;<span class="classifiedId">' + opts.listingNo + '</span></li>';
    }
    info += '<li><strong>İlan Tarihi</strong>&nbsp;<span>' + LISTING_DATE + '</span></li>';
    D.fixedInfo(data.category_path || []).forEach(function (r) {
      info += '<li><strong>' + S.escapeHtml(r[0]) + '</strong>&nbsp;<span>' + S.escapeHtml(r[1]) + '</span></li>';
    });
    var at = data.attributes || {};
    Object.keys(at).forEach(function (k) {
      info += '<li><strong>' + S.escapeHtml(k) + '</strong>&nbsp;<span>' + S.escapeHtml(at[k]) + '</span></li>';
    });
    return '<div class="breadcrumb">' + S.escapeHtml((data.category_path || []).join(' > ')) + '</div>' +
      '<div class="classifiedDetailTitle"><h1>' + S.escapeHtml(data.title) + '</h1></div>' +
      '<div class="classifiedDetailContent">' +
        '<div class="classifiedDetailPhotos"><div class="big-photo">' +
          (photos.length ? S.escapeHtml(photos[0]) : 'Fotoğraf eklenmedi') + '</div>' +
          '<div class="photo-names">' + (photos.length ? photos.length + ' fotoğraf: ' + S.escapeHtml(photos.join(', ')) : '') + '</div>' +
        '</div>' +
        '<div class="classifiedInfo">' +
          '<h3>' + S.formatNumber(data.price) + ' ' + S.escapeHtml(data.currency || 'TL') + '</h3>' +
          '<h2>' + S.escapeHtml([addr.il, addr.ilce, addr.mahalle].filter(Boolean).join(' / ')) + '</h2>' +
          '<ul class="classifiedInfoList">' + info + '</ul>' +
        '</div>' +
      '</div>' +
      '<h3 class="description-title">Açıklama</h3>' +
      '<div id="classifiedDescription">' + descriptionHtml(data) + '</div>';
  }

  /* ---------------- Önizleme ---------------- */
  function previewPage() {
    if (!S.requireLogin()) { return; }
    var draft = ensure('preview');
    if (!draft) { return; }
    $('previewContainer').innerHTML = renderDetail(draft);
    $('btnPreviewBack').addEventListener('click', function () { w.location.href = 'ilan-ver-detay.html'; });
    $('btnPreviewContinue').addEventListener('click', function () {
      var dr = S.getDraft();
      dr.previewed = true;
      S.saveDraft(dr);
      w.location.href = 'ilan-ver-doping.html';
    });
  }

  /* ---------------- Doping ---------------- */
  function dopingPage() {
    if (!S.requireLogin()) { return; }
    var draft = ensure('doping');
    if (!draft) { return; }
    var boxes = d.querySelectorAll('input[name="doping"]');
    var totalEl = $('dopingTotal');
    var err = $('dopingError');
    var selected = draft.dopings_selected || [];
    boxes.forEach(function (b) { b.checked = selected.indexOf(b.value) >= 0; });
    function update() {
      var sum = 0;
      boxes.forEach(function (b) { if (b.checked) { sum += Number(b.getAttribute('data-price')) || 0; } });
      totalEl.textContent = S.formatNumber(sum) + ' TL';
      err.hidden = true;
    }
    boxes.forEach(function (b) { b.addEventListener('change', update); });
    update();
    $('btnBuyDoping').addEventListener('click', function () {
      var chosen = [];
      boxes.forEach(function (b) { if (b.checked) { chosen.push(b.value); } });
      if (!chosen.length) { err.hidden = false; return; }
      var dr = S.getDraft();
      dr.dopings_selected = chosen;
      dr.dopings = [];
      S.saveDraft(dr);
      w.location.href = 'odeme.html';
    });
    $('skipDopingLink').addEventListener('click', function (e) {
      e.preventDefault();
      var dr = S.getDraft();
      dr.dopings_selected = [];
      dr.dopings = [];
      dr.doping_step_done = true;
      S.saveDraft(dr);
      w.location.href = 'ilan-ver-onay.html';
    });
  }

  /* ---------------- Ödeme ---------------- */
  function paymentPage() {
    S.ssSet('visited_payment', '1');
    S.ssSet(S.PAY_KEY, '1');
    if (!S.requireLogin()) { return; }
    var draft = ensure('doping');
    if (!draft) { return; }
    var chosen = draft.dopings_selected || [];
    var prices = { 'Anasayfa Vitrini': 1899, 'Kategori Vitrini': 699, 'Üst Sıradayım': 449, 'Acil Acil': 299, 'Kalın Yazı & Renkli Çerçeve': 149 };
    var sum = chosen.reduce(function (a, n) { return a + (prices[n] || 0); }, 0);
    $('paymentSummary').innerHTML = chosen.length
      ? '<strong>Seçilen dopingler:</strong> ' + S.escapeHtml(chosen.join(', ')) + '<br><strong>Ödenecek Tutar:</strong> ' + S.formatNumber(sum) + ' TL'
      : 'Seçili doping bulunmuyor.';
    var form = $('paymentForm');
    var num = $('cardNumber'), exp = $('cardExpiry'), cvv = $('cardCvv'), holder = $('cardHolder');
    num.addEventListener('input', function () {
      var dg = S.digits(num.value).slice(0, 16);
      var f = dg.replace(/(\d{4})(?=\d)/g, '$1 ');
      if (num.value !== f) { num.value = f; }
    });
    exp.addEventListener('input', function () {
      var dg = S.digits(exp.value).slice(0, 4);
      var f = dg.length > 2 ? dg.slice(0, 2) + '/' + dg.slice(2) : dg;
      if (exp.value !== f) { exp.value = f; }
    });
    function fieldErr(input, msg) {
      var e = input.parentNode.querySelector('.field-error');
      e.textContent = msg || '';
      e.hidden = !msg;
    }
    form.addEventListener('submit', function (e) {
      e.preventDefault();
      var ok = true;
      [holder, num, exp, cvv].forEach(function (i) { fieldErr(i, ''); });
      if (!holder.value.trim()) { fieldErr(holder, REQ); ok = false; }
      var n = S.digits(num.value);
      if (!n) { fieldErr(num, REQ); ok = false; } else if (n.length !== 16) { fieldErr(num, 'Geçerli bir kart numarası giriniz.'); ok = false; }
      if (!exp.value) { fieldErr(exp, REQ); ok = false; } else if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(exp.value)) { fieldErr(exp, 'Geçerli bir son kullanma tarihi giriniz.'); ok = false; }
      var c = S.digits(cvv.value);
      if (!c) { fieldErr(cvv, REQ); ok = false; } else if (c.length < 3) { fieldErr(cvv, 'Geçerli bir CVV giriniz.'); ok = false; }
      if (!ok) { return; }
      S.showOverlay('Ödeme işleniyor...');
      w.setTimeout(function () {
        var dr = S.getDraft();
        dr.dopings = (dr.dopings_selected || []).slice();
        dr.payment_completed = true;
        dr.doping_step_done = true;
        S.saveDraft(dr);
        w.location.href = 'ilan-ver-onay.html';
      }, 500);
    });
  }

  /* ---------------- İlan Onayı ---------------- */
  function confirmPage() {
    if (!S.requireLogin()) { return; }
    var draft = ensure('confirm');
    if (!draft) { return; }
    var addr = draft.address || {};
    var rows = [
      ['Kategori', (draft.category_path || []).join(' > ')],
      ['İlan Başlığı', draft.title],
      ['Fiyat', S.formatNumber(draft.price) + ' ' + (draft.currency || 'TL')],
      ['Adres', [addr.il, addr.ilce, addr.mahalle].filter(Boolean).join(' / ')],
      ['Fotoğraflar', (draft.photos || []).length ? draft.photos.length + ' adet' : 'Fotoğraf eklenmedi'],
      ['Doping', (draft.dopings || []).length ? draft.dopings.join(', ') : 'Doping seçilmedi']
    ];
    $('confirmSummary').innerHTML = rows.map(function (r) {
      return '<tr><th>' + S.escapeHtml(r[0]) + '</th><td>' + S.escapeHtml(r[1]) + '</td></tr>';
    }).join('');
    var chk = $('accuracyConfirm'), err = $('accuracyError'), btn = $('btnPublish');
    chk.addEventListener('change', function () { if (chk.checked) { err.hidden = true; } });
    btn.addEventListener('click', function () {
      if (!chk.checked) { err.hidden = false; return; }
      btn.disabled = true;
      btn.textContent = 'İlan yayınlanıyor...';
      w.setTimeout(function () {
        var dr = S.getDraft();
        var submitted = {
          category_path: dr.category_path || [],
          title: dr.title || '',
          description: dr.description || '',
          price: dr.price || 0,
          currency: dr.currency || 'TL',
          attributes: dr.attributes || {},
          address: { il: (dr.address || {}).il || '', ilce: (dr.address || {}).ilce || '', mahalle: (dr.address || {}).mahalle || '' },
          photos: dr.photos || [],
          terms_accepted: !!dr.terms_accepted,
          accuracy_confirmed: true,
          dopings: dr.dopings || [],
          visited_payment: S.ssGet(S.PAY_KEY) === '1'
        };
        S.ssSet(S.LAST_KEY, JSON.stringify(submitted));
        S.clearDraft();
        w.location.href = 'ilan-ver-tamamlandi.html';
      }, 400);
    });
  }

  function lastSubmitted() {
    try { return JSON.parse(S.ssGet(S.LAST_KEY) || 'null'); } catch (e) { return null; }
  }

  /* ---------------- Tebrikler ---------------- */
  function successPage() {
    if (!S.requireLogin()) { return; }
    var data = lastSubmitted();
    if (!data) { $('successMissing').hidden = false; return; }
    $('mock-submitted').textContent = JSON.stringify(data, null, 2);
    $('successBox').hidden = false;
  }

  /* ---------------- İlanı Görüntüle ---------------- */
  function viewPage() {
    var data = lastSubmitted();
    if (!data) { $('viewContainer').innerHTML = '<p>İlan bulunamadı.</p>'; return; }
    $('viewContainer').innerHTML = renderDetail(data, { listingNo: LISTING_NO });
  }

  var pages = {
    'page-preview': previewPage,
    'page-doping': dopingPage,
    'page-payment': paymentPage,
    'page-confirm': confirmPage,
    'page-success': successPage,
    'page-view': viewPage
  };
  if (pages[page]) { pages[page](); }
})(window, document);
