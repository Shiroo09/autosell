/* letgo mock - single page "ilan ver" flow (no URL changes between steps) */
(function (w, d) {
  'use strict';
  var LG = w.LG;
  var app = d.querySelector('._2kLp0');
  var REQ = 'Bu alan zorunlu';
  var MAX_PHOTOS = 12;

  var CATS = [
    { name: 'Cep Telefonu & Aksesuar', icon: 'phone', subs: ['Cep Telefonu', 'Telefon Aksesuarları', 'Tablet', 'Akıllı Saat'] },
    { name: 'Elektronik', icon: 'tv', subs: ['Bilgisayar', 'Oyun & Konsol', 'TV & Ses Sistemleri', 'Fotoğraf & Kamera'] },
    { name: 'Ev & Bahçe', icon: 'sofa', subs: ['Mobilya', 'Ev Dekorasyonu', 'Beyaz Eşya', 'Bahçe & Yapı Market'] },
    { name: 'Moda & Aksesuar', icon: 'shirt', subs: ['Kadın Giyim', 'Erkek Giyim', 'Ayakkabı', 'Çanta & Cüzdan', 'Saat & Takı'] },
    { name: 'Vasıta', icon: 'car', subs: ['Otomobil', 'Motosiklet', 'Ticari Araç', 'Yedek Parça & Aksesuar'] },
    { name: 'Emlak', icon: 'home', subs: ['Satılık Konut', 'Kiralık Konut', 'Satılık İş Yeri', 'Kiralık İş Yeri', 'Arsa'] },
    { name: 'Bebek & Çocuk', icon: 'baby', subs: ['Bebek Arabası & Puset', 'Oyuncak', 'Bebek & Çocuk Giyim', 'Mama Sandalyesi & Beşik'] },
    { name: 'Spor', icon: 'ball', subs: ['Bisiklet', 'Fitness & Kondisyon', 'Kamp & Outdoor', 'Takım Sporları'] },
    { name: 'Eğlence & Hobi', icon: 'music', subs: ['Kitap & Dergi', 'Müzik Aletleri', 'Film & Müzik', 'Koleksiyon', 'Oyuncak & Hobi'] },
    { name: 'Diğer', icon: 'more', subs: [] }
  ];
  var PHONE_MODELS = {
    'Apple': ['iPhone 11', 'iPhone 11 Pro', 'iPhone 11 Pro Max', 'iPhone 12', 'iPhone 12 mini', 'iPhone 12 Pro', 'iPhone 12 Pro Max',
      'iPhone 13', 'iPhone 13 mini', 'iPhone 13 Pro', 'iPhone 13 Pro Max', 'iPhone 14', 'iPhone 14 Plus', 'iPhone 14 Pro',
      'iPhone 14 Pro Max', 'iPhone 15', 'iPhone 15 Plus', 'iPhone 15 Pro', 'iPhone 15 Pro Max'],
    'Samsung': ['Galaxy S21', 'Galaxy S22', 'Galaxy S23', 'Galaxy S24', 'Galaxy A34', 'Galaxy A54', 'Galaxy Z Flip5'],
    'Xiaomi': ['Redmi Note 12', 'Redmi Note 13', 'Xiaomi 13T', 'Xiaomi 14'],
    'Huawei': ['P30 Lite', 'P40 Lite', 'Nova 11'],
    'Oppo': ['A78', 'Reno 10'],
    'Diğer': ['Diğer']
  };
  var CAR_MODELS = {
    'BMW': ['3 Serisi', '5 Serisi'], 'Fiat': ['Doblo', 'Egea', 'Linea'], 'Ford': ['Fiesta', 'Focus', 'Kuga'],
    'Hyundai': ['i20', 'Tucson'], 'Mercedes-Benz': ['C Serisi', 'E Serisi'], 'Opel': ['Astra', 'Corsa'],
    'Peugeot': ['208', '3008'], 'Renault': ['Captur', 'Clio', 'Megane', 'Taliant'], 'Toyota': ['C-HR', 'Corolla', 'Yaris'],
    'Volkswagen': ['Golf', 'Passat', 'Polo'], 'Diğer': ['Diğer']
  };
  var YEARS = [];
  for (var y = 2026; y >= 1990; y--) { YEARS.push(String(y)); }
  var CONDITIONS = ['Yeni', 'Yeni gibi', 'İyi', 'Makul', 'Hasarlı/Arızalı'];
  var LOCATIONS = ['Kadıköy, İstanbul', 'Kartal, İstanbul', 'Kağıthane, İstanbul', 'Beşiktaş, İstanbul', 'Üsküdar, İstanbul',
    'Ataşehir, İstanbul', 'Maltepe, İstanbul', 'Pendik, İstanbul', 'Şişli, İstanbul', 'Bakırköy, İstanbul', 'Bahçelievler, İstanbul',
    'Beylikdüzü, İstanbul', 'Esenyurt, İstanbul', 'Fatih, İstanbul', 'Sarıyer, İstanbul', 'Çankaya, Ankara', 'Keçiören, Ankara',
    'Yenimahalle, Ankara', 'Etimesgut, Ankara', 'Karşıyaka, İzmir', 'Bornova, İzmir', 'Konak, İzmir', 'Buca, İzmir',
    'Nilüfer, Bursa', 'Osmangazi, Bursa', 'Muratpaşa, Antalya', 'Konyaaltı, Antalya', 'Selçuklu, Konya', 'İzmit, Kocaeli',
    'Tepebaşı, Eskişehir', 'Şahinbey, Gaziantep', 'Yenişehir, Mersin', 'Seyhan, Adana'];

  function icon(p) {
    return '<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="#ff3f55" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + p + '</svg>';
  }
  var ICONS = {
    phone: '<rect x="7" y="2" width="10" height="20" rx="2"/><path d="M11 18h2"/>',
    tv: '<rect x="3" y="5" width="18" height="12" rx="2"/><path d="M8 21h8M12 17v4"/>',
    sofa: '<path d="M4 11V8a2 2 0 012-2h12a2 2 0 012 2v3M3 11h18v6H3zM5 17v2M19 17v2"/>',
    shirt: '<path d="M8 3l4 3 4-3 5 4-3 3v11H6V10L3 7z"/>',
    car: '<path d="M3 13l2-5h14l2 5v5H3zM7 18v2M17 18v2"/>',
    home: '<path d="M3 11l9-7 9 7v10H3zM9 21v-6h6v6"/>',
    baby: '<circle cx="12" cy="8" r="4"/><path d="M5 21c1-4 4-6 7-6s6 2 7 6"/>',
    ball: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    music: '<path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/>',
    more: '<circle cx="5" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="19" cy="12" r="1.5"/>'
  };
  var CHEVRON = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="#999" stroke-width="2"><path d="M9 6l6 6-6 6"/></svg>';
  var CARET = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" fill="none" stroke="#666" stroke-width="2"><path d="M6 9l6 6 6-6"/></svg>';
  var STAR = '<span class="_rq" aria-hidden="true">*</span>';

  var state = { path: [], visitedPayment: false };
  var openList = null; /* currently open custom listbox closer */

  d.addEventListener('mousedown', function (e) {
    if (openList && !openList.owner.contains(e.target)) { openList.close(); }
  });

  function onActivate(el, fn) {
    el.addEventListener('click', fn);
    el.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fn(e); }
    });
  }

  /* ================= step 1: category ================= */
  function renderCategories() {
    state.path = [];
    app.innerHTML = '<h1 class="_5tRe9">Ne satıyorsun?</h1><p class="_2qAs5">' + LG.spinner + 'Kategoriler yükleniyor...</p>';
    w.setTimeout(function () {
      app.innerHTML = '<h1 class="_5tRe9">Ne satıyorsun?</h1><p class="_2qAs5">İlanın için en uygun kategoriyi seç.</p><div class="_8qWe1"></div>';
      var grid = app.querySelector('._8qWe1');
      CATS.forEach(function (c) {
        var card = LG.h('<div role="button" tabindex="0" class="_3xCv5"><span class="_7bNm2">' + icon(ICONS[c.icon]) +
          '</span><span class="_1aSz4">' + LG.esc(c.name) + '</span></div>');
        onActivate(card, function () { chooseTop(c); });
        grid.appendChild(card);
      });
    }, 200);
  }

  function chooseTop(c) {
    if (!c.subs.length) { startForm([c.name]); return; }
    app.innerHTML = '<h1 class="_5tRe9">Ne satıyorsun?</h1><div class="_4yUi6"><button type="button" class="_0oPl3">‹ ' + LG.esc(c.name) +
      '</button><div class="_2qAs5" style="padding:14px 16px;margin:0">' + LG.spinner + 'Yükleniyor...</div></div>';
    app.querySelector('._0oPl3').addEventListener('click', renderCategories);
    w.setTimeout(function () {
      var panel = app.querySelector('._4yUi6');
      if (!panel) { return; }
      panel.lastElementChild.remove();
      c.subs.forEach(function (s) {
        var item = LG.h('<div role="button" tabindex="0" class="_9iKo8"><span>' + LG.esc(s) + '</span>' + CHEVRON + '</div>');
        onActivate(item, function () { startForm([c.name, s]); });
        panel.appendChild(item);
      });
    }, 250);
  }

  /* ================= field components ================= */
  function fieldShell(inner) { return LG.h('<div class="_8nMk4">' + inner + '<div class="_1zXe0" role="alert" hidden></div></div>'); }
  function showError(f, msg) {
    var e = f.el.querySelector(':scope > ._1zXe0');
    e.textContent = msg || '';
    e.hidden = !msg;
    f.el.classList.toggle('_err', !!msg);
  }

  function textField(o) {
    var id = LG.uid();
    var tag = o.multiline
      ? '<textarea id="' + id + '" class="_3aSd6" maxlength="' + o.max + '" placeholder="' + LG.esc(o.placeholder || '') + '"></textarea>'
      : '<input id="' + id + '" class="_3aSd6" type="text" autocomplete="off"' + (o.max ? ' maxlength="' + o.max + '"' : '') +
        (o.numeric ? ' inputmode="numeric"' : '') + ' placeholder="' + LG.esc(o.placeholder || '') + '">';
    var f = { label: o.label };
    f.el = fieldShell('<label class="_5gHj2" for="' + id + '">' + LG.esc(o.label) + STAR + '</label>' + tag +
      (o.max ? '<div class="_7kIo9"><span>' + LG.esc(o.hint || '') + '</span><span class="_2pLm4">0/' + o.max + '</span></div>' : ''));
    var input = f.el.querySelector('#' + CSS.escape(id));
    var counter = f.el.querySelector('._2pLm4');
    input.addEventListener('input', function () {
      if (o.numeric) { var dg = LG.digits(input.value); if (dg !== input.value) { input.value = dg; } }
      if (counter) { counter.textContent = input.value.length + '/' + o.max; }
      showError(f, '');
    });
    f.value = function () { return input.value.trim(); };
    f.validate = function () {
      var v = f.value();
      if (!v) { return REQ; }
      if (o.min && v.length < o.min) { return o.minMsg; }
      return null;
    };
    return f;
  }

  function combo(o) {
    var lid = LG.uid(), bid = LG.uid();
    var f = { label: o.label, selected: '' };
    f.el = fieldShell('<div class="_5gHj2" id="' + lid + '">' + LG.esc(o.label) + STAR + '</div>' +
      '<div class="_6rDs0"><div class="_2nWq8" role="combobox" tabindex="0" aria-haspopup="listbox" aria-expanded="false" aria-labelledby="' + lid +
      '" aria-controls="' + bid + '"><span class="_8xT3v _ph"></span>' + CARET + '</div>' +
      '<div class="_4Hh2c" role="listbox" id="' + bid + '" aria-labelledby="' + lid + '" hidden></div></div>');
    var box = f.el.querySelector('._2nWq8');
    var text = f.el.querySelector('._8xT3v');
    var list = f.el.querySelector('._4Hh2c');
    var options = [];
    var active = -1;
    var closer = { owner: f.el.querySelector('._6rDs0'), close: close };

    function setText(t, ph) { text.textContent = t; text.classList.toggle('_ph', !!ph); }
    function renderOptions() {
      list.innerHTML = '';
      options.forEach(function (opt, i) {
        var oid = bid.replace(/:$/, '') + '-o' + i + ':';
        var el = LG.h('<div role="option" class="_7Yt1s" id="' + oid + '" aria-selected="' + (opt === f.selected) + '">' + LG.esc(opt) + '</div>');
        el.addEventListener('mousedown', function (e) { e.preventDefault(); });
        el.addEventListener('click', function () { choose(opt); });
        list.appendChild(el);
      });
    }
    function highlight(i) {
      var els = list.children;
      if (!els.length) { return; }
      active = Math.max(0, Math.min(i, els.length - 1));
      Array.prototype.forEach.call(els, function (el, k) { el.classList.toggle('_act', k === active); });
      box.setAttribute('aria-activedescendant', els[active].id);
      els[active].scrollIntoView({ block: 'nearest' });
    }
    function open() {
      if (box.getAttribute('aria-disabled') === 'true' || !options.length) { return; }
      if (openList && openList !== closer) { openList.close(); }
      renderOptions();
      list.hidden = false;
      box.setAttribute('aria-expanded', 'true');
      openList = closer;
      highlight(Math.max(0, options.indexOf(f.selected)));
    }
    function close() {
      list.hidden = true;
      box.setAttribute('aria-expanded', 'false');
      box.removeAttribute('aria-activedescendant');
      if (openList === closer) { openList = null; }
    }
    function choose(opt) {
      var changed = opt !== f.selected;
      f.selected = opt;
      setText(opt, false);
      close();
      showError(f, '');
      box.focus();
      if (changed && f.onChange) { f.onChange(opt); }
    }
    box.addEventListener('click', function () { if (list.hidden) { open(); } else { close(); } });
    box.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (list.hidden) { open(); return; }
        highlight(active + (e.key === 'ArrowDown' ? 1 : -1));
      } else if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        if (list.hidden) { open(); } else if (active >= 0) { choose(options[active]); }
      } else if (e.key === 'Escape') {
        close();
      }
    });
    f.setOptions = function (opts) { options = opts.slice(); f.selected = ''; setText(o.placeholder || 'Seç', true); };
    f.setDisabled = function (dis, label) {
      box.setAttribute('aria-disabled', dis ? 'true' : 'false');
      box.tabIndex = dis ? -1 : 0;
      if (label) { setText(label, true); }
    };
    f.value = function () { return f.selected; };
    f.validate = function () { return f.selected ? null : REQ; };
    f.setOptions(o.options || []);
    if (o.disabledText) { f.setDisabled(true, o.disabledText); } else { f.setDisabled(false); }
    return f;
  }

  function chips(o) {
    var lid = LG.uid();
    var f = { label: o.label, selected: '' };
    f.el = fieldShell('<div class="_5gHj2" id="' + lid + '">' + LG.esc(o.label) + STAR + '</div>' +
      '<div class="_5cHp1" role="radiogroup" aria-labelledby="' + lid + '">' +
      o.options.map(function (v, i) {
        return '<button type="button" role="radio" aria-checked="false" tabindex="' + (i === 0 ? 0 : -1) + '" class="_3cHp2">' + LG.esc(v) + '</button>';
      }).join('') + '</div>');
    var btns = Array.prototype.slice.call(f.el.querySelectorAll('._3cHp2'));
    function select(i) {
      f.selected = o.options[i];
      btns.forEach(function (b, k) { b.setAttribute('aria-checked', String(k === i)); b.tabIndex = k === i ? 0 : -1; });
      showError(f, '');
    }
    btns.forEach(function (b, i) {
      b.addEventListener('click', function () { select(i); });
      b.addEventListener('keydown', function (e) {
        if (e.key === 'ArrowRight' || e.key === 'ArrowLeft') {
          e.preventDefault();
          var n = (i + (e.key === 'ArrowRight' ? 1 : btns.length - 1)) % btns.length;
          btns[n].focus();
          select(n);
        }
      });
    });
    f.value = function () { return f.selected; };
    f.validate = function () { return f.selected ? null : REQ; };
    return f;
  }

  function dependentModel(brand, modelField, table) {
    brand.onChange = function (b) {
      modelField.setOptions([]);
      modelField.setDisabled(true, 'Yükleniyor...');
      var token = modelField.token = (modelField.token || 0) + 1;
      w.setTimeout(function () {
        if (token !== modelField.token) { return; }
        modelField.setOptions(table[b] || ['Diğer']);
        modelField.setDisabled(false);
      }, 350);
    };
  }

  function categoryFields(path) {
    var leaf = path[path.length - 1];
    if (leaf === 'Cep Telefonu') {
      var brand = combo({ label: 'Marka', options: Object.keys(PHONE_MODELS), placeholder: 'Marka seç' });
      var model = combo({ label: 'Model', options: [], placeholder: 'Model seç', disabledText: 'Önce marka seç' });
      dependentModel(brand, model, PHONE_MODELS);
      return [brand, model, chips({ label: 'Depolama', options: ['64 GB', '128 GB', '256 GB', '512 GB'] }),
        chips({ label: 'Durum', options: CONDITIONS })];
    }
    if (leaf === 'Otomobil') {
      var cb = combo({ label: 'Marka', options: Object.keys(CAR_MODELS), placeholder: 'Marka seç' });
      var cm = combo({ label: 'Model', options: [], placeholder: 'Model seç', disabledText: 'Önce marka seç' });
      dependentModel(cb, cm, CAR_MODELS);
      return [cb, cm, combo({ label: 'Yıl', options: YEARS, placeholder: 'Yıl seç' }),
        textField({ label: 'Kilometre', numeric: true, placeholder: 'Örn. 85000' }),
        chips({ label: 'Yakıt', options: ['Benzin', 'Dizel', 'LPG', 'Hibrit', 'Elektrik'] }),
        chips({ label: 'Vites', options: ['Manuel', 'Otomatik', 'Yarı otomatik'] })];
    }
    return [chips({ label: 'Durum', options: CONDITIONS })];
  }

  /* ---------------- photos ---------------- */
  function photoField() {
    var f = { label: 'Fotoğraflar', items: [], note: '' };
    f.el = fieldShell('<div class="_3dFg1"><p>Fotoğrafları buraya sürükleyip bırak ya da</p>' +
      '<button type="button" class="_4sDf8">Fotoğraf yükle</button><input type="file" multiple accept="image/*" hidden>' +
      '<p style="margin:10px 0 0;font-size:12px;color:#888">En fazla 12 fotoğraf · İlk fotoğraf kapak fotoğrafı olur</p></div>' +
      '<div class="_7hJk5"></div><div class="_7kIo9"><span class="_pNote"></span><span class="_2pLm4">0/12</span></div>');
    var drop = f.el.querySelector('._3dFg1');
    var input = f.el.querySelector('input[type=file]');
    var grid = f.el.querySelector('._7hJk5');
    function render() {
      grid.innerHTML = '';
      f.items.forEach(function (p, i) {
        var t = LG.h('<div class="_5kLo2">' + (p.url ? '<img alt="" src="' + p.url + '">' : '') +
          (i === 0 ? '<span class="_8rEw3">Kapak</span>' : '') +
          '<button type="button" class="_2uYt6" aria-label="Fotoğrafı kaldır">×</button>' +
          (p.uploading ? '<div class="_0tYh7">' + LG.spinner + '</div>' : '') +
          '<span class="_fn">' + LG.esc(p.name) + '</span></div>');
        var img = t.querySelector('img');
        if (img) { img.addEventListener('error', function () { img.remove(); }); }
        t.querySelector('._2uYt6').addEventListener('click', function () { f.items.splice(f.items.indexOf(p), 1); f.note = ''; render(); });
        grid.appendChild(t);
      });
      f.el.querySelector('._2pLm4').textContent = f.items.length + '/' + MAX_PHOTOS;
      f.el.querySelector('._pNote').textContent = f.note;
    }
    function add(files) {
      f.note = '';
      var n = 0;
      Array.prototype.forEach.call(files, function (file) {
        if (f.items.length >= MAX_PHOTOS) { f.note = 'En fazla 12 fotoğraf yükleyebilirsin'; return; }
        if (!(file.type && file.type.indexOf('image/') === 0) && !/\.(jpe?g|png|gif|webp|heic|bmp|svg)$/i.test(file.name)) {
          f.note = 'Sadece fotoğraf yükleyebilirsin: ' + file.name;
          return;
        }
        var p = { name: file.name, uploading: true, url: null };
        try { p.url = URL.createObjectURL(file); } catch (e) { p.url = null; }
        f.items.push(p);
        w.setTimeout(function () { p.uploading = false; render(); }, 350 + 150 * n);
        n++;
      });
      showError(f, '');
      render();
    }
    f.el.querySelector('._4sDf8').addEventListener('click', function () { input.click(); });
    input.addEventListener('change', function () { add(input.files || []); input.value = ''; });
    drop.addEventListener('dragover', function (e) { e.preventDefault(); drop.classList.add('_drag'); });
    drop.addEventListener('dragleave', function () { drop.classList.remove('_drag'); });
    drop.addEventListener('drop', function (e) {
      e.preventDefault();
      drop.classList.remove('_drag');
      if (e.dataTransfer && e.dataTransfer.files) { add(e.dataTransfer.files); }
    });
    f.value = function () { return f.items.map(function (p) { return p.name; }); };
    f.validate = function () {
      if (f.items.some(function (p) { return p.uploading; })) { return 'Fotoğraflar yükleniyor, lütfen bekle'; }
      return f.items.length ? null : REQ;
    };
    render();
    return f;
  }

  /* ---------------- price + negotiable ---------------- */
  function priceField() {
    var f = { label: 'Fiyat' };
    f.el = fieldShell('<label style="display:block"><span class="_5gHj2">Fiyat' + STAR + '</span>' +
      '<span class="_4pRc1"><span class="_7pRc2">₺</span><input class="_3aSd6" type="text" inputmode="numeric" autocomplete="off" placeholder="Fiyat gir"></span></label>');
    var input = f.el.querySelector('input');
    input.addEventListener('input', function () {
      var dg = LG.digits(input.value).replace(/^0+(?=\d)/, '').slice(0, 10);
      var v = dg ? LG.dots(dg) : '';
      if (input.value !== v) { input.value = v; }
      showError(f, '');
    });
    f.value = function () { return Number(LG.digits(input.value)) || 0; };
    f.validate = function () { return f.value() > 0 ? null : REQ; };
    return f;
  }
  function switchField() {
    var el = LG.h('<label class="_2sWt1"><span>Pazarlık payı var</span><span class="_6sWt2">' +
      '<input type="checkbox" role="switch" class="_1sWt3"><span class="_8sWt4"><span class="_3sWt5"></span></span></span></label>');
    return { el: el, value: function () { return el.querySelector('input').checked; } };
  }

  /* ---------------- location autocomplete ---------------- */
  function fold(s) {
    return s.toLocaleLowerCase('tr-TR').replace(/ç/g, 'c').replace(/ğ/g, 'g').replace(/ı/g, 'i').replace(/i̇/g, 'i')
      .replace(/ö/g, 'o').replace(/ş/g, 's').replace(/ü/g, 'u');
  }
  function locationField() {
    var id = LG.uid(), lb = LG.uid();
    var f = { label: 'Konum', chosen: null };
    f.el = fieldShell('<label class="_5gHj2" for="' + id + '">Konum' + STAR + '</label><div class="_6rDs0">' +
      '<input id="' + id + '" class="_3aSd6" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="' + lb +
      '" autocomplete="off" placeholder="Semt, ilçe veya il yaz">' +
      '<div class="_4Hh2c" role="listbox" id="' + lb + '" aria-label="Konum önerileri" hidden></div></div>' +
      '<div class="_7kIo9"><button type="button" class="_9lKj5">Mevcut konumumu kullan</button></div>');
    var input = f.el.querySelector('input');
    var list = f.el.querySelector('._4Hh2c');
    var timer = null, active = -1, results = [];
    var closer = { owner: f.el.querySelector('._6rDs0'), close: close };
    function close() { list.hidden = true; input.setAttribute('aria-expanded', 'false'); if (openList === closer) { openList = null; } }
    function choose(v) { f.chosen = v; input.value = v; close(); showError(f, ''); }
    function show(items) {
      results = items;
      active = -1;
      list.innerHTML = items.length ? '' : '<div class="_7Yt1s" style="color:#888">Sonuç bulunamadı</div>';
      items.forEach(function (v) {
        var o = LG.h('<div role="option" class="_7Yt1s" aria-selected="false">' + LG.esc(v) + '</div>');
        o.addEventListener('mousedown', function (e) { e.preventDefault(); });
        o.addEventListener('click', function () { choose(v); });
        list.appendChild(o);
      });
      if (openList && openList !== closer) { openList.close(); }
      list.hidden = false;
      input.setAttribute('aria-expanded', 'true');
      openList = closer;
    }
    input.addEventListener('input', function () {
      f.chosen = null;
      showError(f, '');
      w.clearTimeout(timer);
      var q = fold(input.value.trim());
      if (q.length < 2) { close(); return; }
      timer = w.setTimeout(function () {
        var starts = [], contains = [];
        LOCATIONS.forEach(function (l) {
          var fl = fold(l);
          if (fl.indexOf(q) === 0) { starts.push(l); } else if (fl.indexOf(q) > 0) { contains.push(l); }
        });
        show(starts.concat(contains).slice(0, 8));
      }, 300);
    });
    input.addEventListener('keydown', function (e) {
      var opts = list.querySelectorAll('[role=option]');
      if (list.hidden || !opts.length) { return; }
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        active = Math.max(0, Math.min(opts.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1)));
        opts.forEach(function (o, i) { o.classList.toggle('_act', i === active); });
      } else if (e.key === 'Enter' && active >= 0) {
        e.preventDefault();
        choose(results[active]);
      } else if (e.key === 'Escape') { close(); }
    });
    input.addEventListener('blur', function () { w.setTimeout(close, 150); });
    f.el.querySelector('._9lKj5').addEventListener('click', function () {
      showError(f, 'Konum izni alınamadı. Lütfen konumu listeden seç.');
    });
    f.value = function () { return f.chosen; };
    f.validate = function () {
      if (f.chosen) { return null; }
      return input.value.trim() ? 'Listeden bir konum seçmelisin' : REQ;
    };
    return f;
  }

  /* ================= step 2: form ================= */
  function section(title) {
    var s = LG.h('<section class="_1mNb0"><h2>' + LG.esc(title) + '</h2></section>');
    app.appendChild(s);
    return s;
  }

  function startForm(path) {
    state.path = path;
    app.innerHTML = '';
    var crumb = LG.h('<div class="_2hGf7"><span>Kategori:</span><span class="_crumb">' + LG.esc(path.join(' › ')) +
      '</span><a href="#" class="_9lKj5">Değiştir</a></div>');
    crumb.querySelector('a').addEventListener('click', function (e) { e.preventDefault(); renderCategories(); });
    app.appendChild(crumb);
    app.appendChild(LG.h('<h1 class="_5tRe9">İlan detaylarını gir</h1>'));

    var photos = photoField();
    section('Fotoğraflar').appendChild(photos.el);

    var info = section('Ürün bilgileri');
    var title = textField({ label: 'Başlık', max: 70, min: 5, minMsg: 'Başlık en az 5 karakter olmalı', hint: 'Ürününün en önemli özelliklerini yaz', placeholder: 'Örn. iPhone 13 128 GB, temiz kullanılmış' });
    var desc = textField({ label: 'Açıklama', max: 4096, min: 10, minMsg: 'Açıklama en az 10 karakter olmalı', multiline: true, hint: 'Ürünün durumu, özellikleri ve satış nedeni', placeholder: 'Ürününü detaylı anlat' });
    info.appendChild(title.el);
    info.appendChild(desc.el);

    var catFields = categoryFields(path);
    var feat = section('Özellikler');
    catFields.forEach(function (f) { feat.appendChild(f.el); });

    var priceSec = section('Fiyat');
    var price = priceField();
    var neg = switchField();
    priceSec.appendChild(price.el);
    priceSec.appendChild(neg.el);

    var loc = locationField();
    section('Konum').appendChild(loc.el);

    var summary = LG.h('<div class="_3tSt1" role="alert" hidden>Lütfen işaretli alanları kontrol et.</div>');
    var publish = LG.h('<button type="button" class="_1pQr7 _3wEr0">İlanı Yayınla</button>');
    app.appendChild(summary);
    app.appendChild(publish);

    var all = [photos, title, desc].concat(catFields).concat([price, loc]);
    publish.addEventListener('click', function () {
      var first = null;
      all.forEach(function (f) {
        var msg = f.validate();
        showError(f, msg);
        if (msg && !first) { first = f; }
      });
      if (first) {
        summary.hidden = false;
        first.el.scrollIntoView({ block: 'center' });
        return;
      }
      summary.hidden = true;
      publish.disabled = true;
      publish.innerHTML = LG.spinner + 'Yayınlanıyor...';
      var attributes = {};
      catFields.forEach(function (f) { if (f.value()) { attributes[f.label] = f.value(); } });
      state.data = {
        category_path: path.slice(),
        title: title.value(),
        description: desc.value(),
        price: price.value(),
        negotiable: neg.value(),
        attributes: attributes,
        location: loc.value(),
        photos: photos.value()
      };
      w.setTimeout(showUpsell, 500);
    });
  }

  /* ================= upsell, payment, success ================= */
  function showUpsell() {
    var m = LG.modal('<h2 class="_6tYu3" id="{{TITLE_ID}}">İlanını öne çıkar, 10 kat daha fazla görüntülenme!</h2>' +
      '<p class="_2qAs5">Öne çıkan ilanlar listelerin en üstünde gösterilir ve çok daha hızlı satılır.</p>' +
      '<ul class="_5upS1"><li>7 gün boyunca aramalarda en üstte</li><li>Dikkat çeken "ÖNE ÇIKAN" etiketi</li><li>10 kata kadar daha fazla görüntülenme</li></ul>' +
      '<div class="_2mDk7"><button type="button" class="_1pQr7 _3wEr0 _buy">Öne Çıkar – ₺49,99</button>' +
      '<button type="button" class="_4sDf8 _3wEr0 _skip">Şimdi değil</button></div>',
      { onDismiss: function () { finish(false); } });
    m.el.querySelector('._buy').addEventListener('click', function () { m.close(); showPayment(); });
    m.el.querySelector('._skip').addEventListener('click', function () { m.close(); finish(false); });
  }

  function showPayment() {
    state.visitedPayment = true;
    LG.ssSet(LG.PAY_KEY, '1');
    LG.ssSet('visited_payment', '1');
    var ids = [LG.uid(), LG.uid(), LG.uid(), LG.uid()];
    var labels = ['Kart numarası', 'Son kullanma tarihi', 'CVV', 'Kart üzerindeki isim'];
    var ph = ['0000 0000 0000 0000', 'AA/YY', '123', 'Ad Soyad'];
    var fields = labels.map(function (l, i) {
      return '<div class="_8nMk4"><label class="_5gHj2" for="' + ids[i] + '">' + l + '</label><input id="' + ids[i] +
        '" class="_3aSd6" type="text" autocomplete="off" placeholder="' + ph[i] + '"><div class="_1zXe0" role="alert" hidden></div></div>';
    }).join('');
    var m = LG.modal('<h2 class="_6tYu3" id="{{TITLE_ID}}">Ödeme</h2><p class="_2qAs5">Öne Çıkar paketi (7 gün): <b>₺49,99</b></p>' + fields +
      '<div class="_2mDk7"><button type="button" class="_1pQr7 _3wEr0 _pay">₺49,99 Öde</button><button type="button" class="_4sDf8 _3wEr0 _back">Vazgeç</button></div>',
      { onDismiss: function () { showUpsell(); } });
    var inputs = ids.map(function (i) { return m.el.querySelector('#' + CSS.escape(i)); });
    inputs[0].addEventListener('input', function () {
      var v = LG.digits(inputs[0].value).slice(0, 16).replace(/(\d{4})(?=\d)/g, '$1 ');
      if (inputs[0].value !== v) { inputs[0].value = v; }
    });
    inputs[1].addEventListener('input', function () {
      var dg = LG.digits(inputs[1].value).slice(0, 4);
      var v = dg.length > 2 ? dg.slice(0, 2) + '/' + dg.slice(2) : dg;
      if (inputs[1].value !== v) { inputs[1].value = v; }
    });
    m.el.querySelector('._back').addEventListener('click', function () { m.close(); showUpsell(); });
    m.el.querySelector('._pay').addEventListener('click', function () {
      var checks = [LG.digits(inputs[0].value).length === 16, /^(0[1-9]|1[0-2])\/\d{2}$/.test(inputs[1].value),
        /^\d{3,4}$/.test(inputs[2].value.trim()), !!inputs[3].value.trim()];
      var ok = true;
      checks.forEach(function (c, i) {
        var e = inputs[i].parentNode.querySelector('._1zXe0');
        e.textContent = c ? '' : (inputs[i].value.trim() ? 'Geçersiz bilgi' : REQ);
        e.hidden = c;
        if (!c) { ok = false; }
      });
      if (!ok) { return; }
      var b = m.el.querySelector('._pay');
      b.disabled = true;
      b.innerHTML = LG.spinner + 'İşleniyor...';
      w.setTimeout(function () { m.close(); finish(true); }, 600);
    });
  }

  function finish(promoted) {
    var data = state.data;
    if (!data) { return; }
    state.data = null;
    var submitted = {
      category_path: data.category_path,
      title: data.title,
      description: data.description,
      price: data.price,
      negotiable: data.negotiable,
      attributes: data.attributes,
      location: data.location,
      photos: data.photos,
      promoted: !!promoted,
      visited_payment: state.visitedPayment || LG.ssGet(LG.PAY_KEY) === '1'
    };
    LG.ssSet(LG.LAST_KEY, JSON.stringify(submitted));
    app.innerHTML = '<div class="_1sCc1"><div class="_4sCc2" aria-hidden="true">✓</div><h1>İlanın yayında! 🎉</h1>' +
      '<p class="_2qAs5">Alıcılar artık ilanını görebilir. Gelen mesajları Sohbetler bölümünden takip edebilirsin.</p>' +
      (promoted ? '<p><b>İlanın 7 gün boyunca öne çıkarılacak.</b></p>' : '') +
      '<div class="_9sKe1"><a class="_4sDf8" href="' + LG.root + 'index.html">Ana sayfaya dön</a><a class="_1pQr7" href="' + LG.root + 'post/">Yeni ilan ver</a></div>' +
      '<div class="_6sCc3"><div class="_cap">Gönderilen veriler (test)</div><pre id="mock-submitted"></pre></div></div>';
    d.getElementById('mock-submitted').textContent = JSON.stringify(submitted, null, 2);
    w.scrollTo(0, 0);
  }

  /* ================= boot (login gate) ================= */
  if (LG.isLoggedIn()) {
    renderCategories();
  } else {
    app.innerHTML = '<div class="_1mNb0" style="padding:22px"><h1 class="_5tRe9">İlan vermek için giriş yap</h1>' +
      '<p class="_2qAs5">Ücretsiz ilan verebilmek için telefon numaranla giriş yapman gerekiyor.</p></div>';
    LG.openLogin({
      onSuccess: renderCategories,
      onCancel: function () { w.location.href = LG.root + 'index.html'; }
    });
  }
})(window, document);
