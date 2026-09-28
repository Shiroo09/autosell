/* letgo mock - shared runtime: auth state, login modal, cookie bar, header search */
(function (w, d) {
  'use strict';
  var LG = {
    LOGIN_KEY: 'mock_letgo_login',
    COOKIE_KEY: 'mock_letgo_cookie',
    PAY_KEY: 'mock_letgo_visited_payment',
    LAST_KEY: 'mock_letgo_last_submitted'
  };
  var script = d.currentScript;
  LG.root = script ? script.src.replace(/assets\/core\.js.*$/, '') : '';

  function st(kind) { try { return kind === 'l' ? w.localStorage : w.sessionStorage; } catch (e) { return null; } }
  function get(kind, k) { try { var s = st(kind); return s ? s.getItem(k) : null; } catch (e) { return null; } }
  function set(kind, k, v) { try { var s = st(kind); if (s) { s.setItem(k, v); } } catch (e) { /* ignore */ } }
  function del(kind, k) { try { var s = st(kind); if (s) { s.removeItem(k); } } catch (e) { /* ignore */ } }
  LG.lsGet = function (k) { return get('l', k); };
  LG.lsSet = function (k, v) { set('l', k, v); };
  LG.ssGet = function (k) { return get('s', k); };
  LG.ssSet = function (k, v) { set('s', k, v); };
  LG.ssDel = function (k) { del('s', k); };

  LG.isLoggedIn = function () { return get('l', LG.LOGIN_KEY) === '1'; };
  LG.login = function () { set('l', LG.LOGIN_KEY, '1'); };
  LG.logout = function () { del('l', LG.LOGIN_KEY); };

  var idc = 0;
  LG.uid = function () { idc += 1; return ':r' + idc.toString(36) + ':'; };
  LG.esc = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  LG.h = function (html) {
    var t = d.createElement('template');
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  };
  LG.digits = function (s) { return String(s == null ? '' : s).replace(/\D+/g, ''); };
  LG.dots = function (n) { return String(n).replace(/\B(?=(\d{3})+(?!\d))/g, '.'); };
  LG.spinner = '<span class="_0spn1" aria-hidden="true"></span>';

  /* ---------------- generic modal ---------------- */
  LG.modal = function (innerHtml, opts) {
    opts = opts || {};
    var titleId = LG.uid();
    var overlay = LG.h('<div class="_4xRe2"><div class="_9pQw1" role="dialog" aria-modal="true" aria-labelledby="' + titleId + '">' +
      '<button type="button" class="_1cVb7" aria-label="Kapat">×</button>' +
      innerHtml.replace('{{TITLE_ID}}', titleId) + '</div></div>');
    var box = overlay.firstElementChild;
    function close(reason) {
      if (!overlay.isConnected) { return; }
      overlay.remove();
      d.removeEventListener('keydown', onKey);
      if (reason && opts.onDismiss) { opts.onDismiss(reason); }
    }
    function onKey(e) { if (e.key === 'Escape' && opts.dismissable !== false) { close('escape'); } }
    box.querySelector('._1cVb7').addEventListener('click', function () { close('close'); });
    overlay.addEventListener('mousedown', function (e) {
      if (e.target === overlay && opts.dismissable !== false) { close('backdrop'); }
    });
    d.addEventListener('keydown', onKey);
    d.body.appendChild(overlay);
    return { el: box, close: close };
  };

  /* ---------------- login modal (phone -> 4 digit code) ---------------- */
  LG.openLogin = function (opts) {
    opts = opts || {};
    var phoneId = LG.uid(), codeId = LG.uid();
    var m = LG.modal(
      '<h2 class="_6tYu3" id="{{TITLE_ID}}">Giriş yap veya kayıt ol</h2>' +
      '<div class="_step1">' +
        '<p class="_2qAs5">Devam etmek için telefon numaranı gir. Sana SMS ile bir doğrulama kodu göndereceğiz.</p>' +
        '<div class="_8nMk4"><label class="_5gHj2" for="' + phoneId + '">Telefon numarası</label>' +
          '<div class="_4pRc1"><span class="_7pRc2">+90</span><input id="' + phoneId + '" class="_3aSd6" type="tel" inputmode="tel" placeholder="5XX XXX XX XX" autocomplete="tel-national"></div>' +
          '<div class="_1zXe0" role="alert" hidden></div></div>' +
        '<button type="button" class="_1pQr7 _3wEr0 _go1">Devam</button>' +
      '</div>' +
      '<div class="_step2" hidden>' +
        '<p class="_2qAs5 _sent"></p>' +
        '<div class="_8nMk4"><label class="_5gHj2" for="' + codeId + '">Doğrulama kodu</label>' +
          '<input id="' + codeId + '" class="_3aSd6" type="text" inputmode="numeric" maxlength="4" autocomplete="one-time-code" placeholder="4 haneli kod">' +
          '<div class="_1zXe0" role="alert" hidden></div></div>' +
        '<button type="button" class="_1pQr7 _3wEr0 _go2">Giriş Yap</button>' +
        '<p style="text-align:center;margin:12px 0 0"><button type="button" class="_9lKj5 _resend">Kodu tekrar gönder</button></p>' +
      '</div>' +
      '<p style="font-size:12px;color:#888;margin:16px 0 0">Devam ederek Kullanım Koşulları ve Gizlilik Politikası\'nı kabul etmiş olursun.</p>',
      { onDismiss: function () { if (opts.onCancel) { opts.onCancel(); } }, dismissable: opts.dismissable }
    );
    var box = m.el;
    var phone = box.querySelector('#' + CSS.escape(phoneId));
    var code = box.querySelector('#' + CSS.escape(codeId));
    var go1 = box.querySelector('._go1'), go2 = box.querySelector('._go2');
    function err(input, msg) {
      var wrap = input.closest('._8nMk4');
      var e = wrap.querySelector('._1zXe0');
      e.textContent = msg || '';
      e.hidden = !msg;
      wrap.classList.toggle('_err', !!msg);
    }
    phone.addEventListener('input', function () { err(phone, ''); });
    code.addEventListener('input', function () { err(code, ''); });
    function step1() {
      var raw = phone.value.trim();
      if (!raw) { err(phone, 'Telefon numaranı gir'); return; }
      var dg = LG.digits(raw).replace(/^90(?=\d{10}$)/, '').replace(/^0(?=\d{10}$)/, '');
      go1.disabled = true;
      go1.innerHTML = LG.spinner + 'Kod gönderiliyor...';
      w.setTimeout(function () {
        box.querySelector('._step1').hidden = true;
        box.querySelector('._step2').hidden = false;
        var shown = dg.length === 10 ? dg.slice(0, 3) + ' ' + dg.slice(3, 6) + ' ' + dg.slice(6, 8) + ' ' + dg.slice(8) : raw;
        box.querySelector('._sent').innerHTML = '<b>+90 ' + LG.esc(shown) + '</b> numarasına gönderdiğimiz 4 haneli kodu gir.';
        code.focus();
      }, 400);
    }
    function step2() {
      if (!code.value.trim()) { err(code, 'Doğrulama kodunu gir'); return; }
      go2.disabled = true;
      go2.innerHTML = LG.spinner + 'Giriş yapılıyor...';
      w.setTimeout(function () {
        LG.login();
        m.close();
        LG.renderAuth();
        if (opts.onSuccess) { opts.onSuccess(); }
      }, 300);
    }
    go1.addEventListener('click', step1);
    go2.addEventListener('click', step2);
    phone.addEventListener('keydown', function (e) { if (e.key === 'Enter') { step1(); } });
    code.addEventListener('keydown', function (e) { if (e.key === 'Enter') { step2(); } });
    box.querySelector('._resend').addEventListener('click', function () { err(code, ''); code.value = ''; });
    w.setTimeout(function () { phone.focus(); }, 0);
    return m;
  };

  /* ---------------- header auth area ---------------- */
  LG.renderAuth = function () {
    var logged = LG.isLoggedIn();
    d.querySelectorAll('._2wEr5').forEach(function (b) { b.hidden = logged; });
    d.querySelectorAll('._uWrap').forEach(function (u) { u.hidden = !logged; });
  };

  function initHeader() {
    d.querySelectorAll('._2wEr5').forEach(function (b) {
      b.addEventListener('click', function () { LG.openLogin({}); });
    });
    d.querySelectorAll('._uWrap').forEach(function (u) {
      var btn = u.querySelector('._6yHn0');
      var menu = u.querySelector('._3mVb8');
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        menu.hidden = !menu.hidden;
        btn.setAttribute('aria-expanded', String(!menu.hidden));
      });
      d.addEventListener('click', function () { menu.hidden = true; btn.setAttribute('aria-expanded', 'false'); });
      var out = u.querySelector('._lgout');
      if (out) {
        out.addEventListener('click', function () { LG.logout(); w.location.reload(); });
      }
    });
    d.querySelectorAll('._1sQe8').forEach(function (inp) {
      function go() {
        var v = inp.value.trim();
        w.location.href = LG.root + 'arama.html' + (v ? '?q=' + encodeURIComponent(v) : '');
      }
      inp.addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); go(); } });
      var b = inp.parentNode.querySelector('._5bNw4');
      if (b) { b.addEventListener('click', go); }
    });
    LG.renderAuth();
  }

  /* ---------------- cookie bar ---------------- */
  function cookieBar() {
    if (LG.lsGet(LG.COOKIE_KEY)) { return; }
    var bar = LG.h('<div class="_0cKi9" role="region" aria-label="Çerez bildirimi">' +
      '<p>Sana daha iyi bir deneyim sunmak, içerikleri kişiselleştirmek ve trafiğimizi analiz etmek için çerezleri kullanıyoruz.</p>' +
      '<div class="_7zKt2"><button type="button" class="_setC">Ayarlar</button><button type="button" class="_okC">Kabul et</button></div></div>');
    bar.querySelector('._okC').addEventListener('click', function () { LG.lsSet(LG.COOKIE_KEY, 'all'); bar.remove(); });
    bar.querySelector('._setC').addEventListener('click', function () { LG.lsSet(LG.COOKIE_KEY, 'essential'); bar.remove(); });
    d.body.appendChild(bar);
  }

  w.LG = LG;
  function init() { initHeader(); cookieBar(); }
  if (d.readyState === 'loading') { d.addEventListener('DOMContentLoaded', init); } else { init(); }
})(window, document);
