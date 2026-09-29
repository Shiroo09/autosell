/* sahibinden.com mock - shared helpers (header state, cookie banner, storage) */
(function (w, d) {
  'use strict';

  var S = {
    LOGIN_KEY: 'mock_sahibinden_login',
    USER_KEY: 'mock_sahibinden_user',
    COOKIE_KEY: 'mock_sahibinden_cookie_consent',
    DRAFT_KEY: 'mock_sahibinden_draft',
    LAST_KEY: 'mock_sahibinden_last_submitted',
    PAY_KEY: 'mock_sahibinden_visited_payment',
    USER_NAME: 'Deniz Y.'
  };

  function store(kind) {
    try { return kind === 'local' ? w.localStorage : w.sessionStorage; } catch (e) { return null; }
  }
  S.lsGet = function (k) { try { var s = store('local'); return s ? s.getItem(k) : null; } catch (e) { return null; } };
  S.lsSet = function (k, v) { try { var s = store('local'); if (s) { s.setItem(k, v); } } catch (e) { /* ignore */ } };
  S.lsDel = function (k) { try { var s = store('local'); if (s) { s.removeItem(k); } } catch (e) { /* ignore */ } };
  S.ssGet = function (k) { try { var s = store('session'); return s ? s.getItem(k) : null; } catch (e) { return null; } };
  S.ssSet = function (k, v) { try { var s = store('session'); if (s) { s.setItem(k, v); } } catch (e) { /* ignore */ } };
  S.ssDel = function (k) { try { var s = store('session'); if (s) { s.removeItem(k); } } catch (e) { /* ignore */ } };

  S.params = function () { return new URLSearchParams(w.location.search); };
  S.root = function () { return d.body.getAttribute('data-root') || ''; };

  S.isLoggedIn = function () { return S.lsGet(S.LOGIN_KEY) === '1'; };
  S.login = function () { S.lsSet(S.LOGIN_KEY, '1'); S.lsSet(S.USER_KEY, S.USER_NAME); };
  S.logout = function () { S.lsDel(S.LOGIN_KEY); S.lsDel(S.USER_KEY); };

  /* Only relative, same-site return targets are accepted. */
  S.safeReturn = function (r) {
    if (!r) { return null; }
    if (/^[A-Za-z0-9_\-\/\.]+\.html(\?[^#]*)?$/.test(r) && r.indexOf('..') < 0 && r.indexOf('//') < 0 && r.charAt(0) !== '/') {
      return r;
    }
    return null;
  };

  /* Posting pages call this first; redirects to giris.html?return=... when logged out. */
  S.requireLogin = function () {
    if (S.isLoggedIn()) { return true; }
    var here = w.location.pathname.split('/').pop() || 'index.html';
    var ret = here + w.location.search;
    w.location.replace(S.root() + 'giris.html?return=' + encodeURIComponent(ret));
    return false;
  };

  S.getDraft = function () {
    try { return JSON.parse(S.ssGet(S.DRAFT_KEY) || '{}') || {}; } catch (e) { return {}; }
  };
  S.saveDraft = function (draft) { S.ssSet(S.DRAFT_KEY, JSON.stringify(draft)); };
  S.clearDraft = function () { S.ssDel(S.DRAFT_KEY); };

  S.escapeHtml = function (s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  };
  S.formatNumber = function (n) {
    var s = String(Math.floor(Number(n) || 0));
    return s.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  };
  S.digits = function (s) { return String(s == null ? '' : s).replace(/\D+/g, ''); };

  /* Very small whitelist sanitizer for the rich text description. */
  S.sanitizeHtml = function (html) {
    var tpl = d.createElement('template');
    tpl.innerHTML = html || '';
    var allowed = { B: 1, STRONG: 1, I: 1, EM: 1, U: 1, UL: 1, OL: 1, LI: 1, BR: 1, P: 1, DIV: 1, SPAN: 1 };
    (function walk(node) {
      var kids = Array.prototype.slice.call(node.childNodes);
      kids.forEach(function (k) {
        if (k.nodeType === 1) {
          if (!allowed[k.tagName]) {
            if (k.tagName === 'SCRIPT' || k.tagName === 'STYLE' || k.tagName === 'IFRAME') { k.remove(); return; }
            walk(k);
            while (k.firstChild) { node.insertBefore(k.firstChild, k); }
            k.remove();
            return;
          }
          Array.prototype.slice.call(k.attributes).forEach(function (a) { k.removeAttribute(a.name); });
          walk(k);
        } else if (k.nodeType !== 3) {
          k.remove();
        }
      });
    })(tpl.content);
    return tpl.innerHTML;
  };

  S.showOverlay = function (text) {
    var o = d.createElement('div');
    o.className = 'saving-overlay';
    o.innerHTML = '<div><span class="spinner"></span>' + S.escapeHtml(text) + '</div>';
    d.body.appendChild(o);
    return o;
  };

  /* ---------------- header login state ---------------- */
  function applyHeader() {
    var logged = S.isLoggedIn();
    d.querySelectorAll('.guest-only').forEach(function (el) { el.hidden = logged; });
    d.querySelectorAll('.user-only').forEach(function (el) { el.hidden = !logged; });
    d.querySelectorAll('.user-name').forEach(function (el) { el.textContent = S.lsGet(S.USER_KEY) || S.USER_NAME; });
    var q = S.params().get('query_text');
    if (q !== null) {
      d.querySelectorAll('input[name="query_text"]').forEach(function (el) { el.value = q; });
    }
  }

  /* ---------------- cookie consent banner ---------------- */
  function cookieBanner() {
    if (S.lsGet(S.COOKIE_KEY) === 'accepted') { return; }
    var root = S.root();
    var el = d.createElement('div');
    el.className = 'cookie-consent';
    el.id = 'cookieConsent';
    el.setAttribute('role', 'region');
    el.setAttribute('aria-label', 'Çerez bildirimi');
    el.innerHTML =
      '<div class="cookie-consent-inner">' +
        '<div class="cookie-consent-text">' +
          '<strong>Çerezleri Kullanıyoruz</strong>' +
          '<p>sahibinden.com olarak sitemizin düzgün çalışmasını sağlamak, deneyiminizi kişiselleştirmek, ' +
          'site trafiğini analiz etmek ve size ilgi alanlarınıza uygun reklamlar gösterebilmek için çerezler ' +
          'kullanmaktayız. Zorunlu çerezler dışındaki çerezleri kullanabilmemiz için onayınıza ihtiyaç duyuyoruz.</p>' +
          '<p>Çerezlerle ilgili detaylı bilgiye <a href="' + root + 'yardim.html#cerez-politikasi">Çerez Aydınlatma Metni</a> ' +
          'üzerinden ulaşabilir, tercihlerinizi dilediğiniz zaman <a href="' + root + 'yardim.html#cerez-tercihleri">Çerez Tercihleri</a> ' +
          'sayfasından değiştirebilirsiniz. "Kabul Et" butonuna tıklayarak tüm çerezlerin kullanımına izin vermiş olursunuz.</p>' +
          '<div class="cookie-settings-panel" hidden>Zorunlu çerezler her zaman aktiftir. Performans ve reklam çerezleri yalnızca onayınızla kullanılır.</div>' +
        '</div>' +
        '<div class="cookie-consent-actions">' +
          '<button type="button" class="btn btn-primary btn-cookie-accept">Kabul Et</button>' +
          '<button type="button" class="btn btn-secondary btn-cookie-settings">Çerez Ayarları</button>' +
        '</div>' +
      '</div>';
    d.body.appendChild(el);
    el.querySelector('.btn-cookie-accept').addEventListener('click', function () {
      S.lsSet(S.COOKIE_KEY, 'accepted');
      el.remove();
    });
    el.querySelector('.btn-cookie-settings').addEventListener('click', function () {
      var p = el.querySelector('.cookie-settings-panel');
      p.hidden = !p.hidden;
    });
  }

  function handleLogoutParam() {
    var p = S.params();
    if (p.get('cikis') === '1') {
      S.logout();
      p.delete('cikis');
      var qs = p.toString();
      try { w.history.replaceState(null, '', w.location.pathname + (qs ? '?' + qs : '')); } catch (e) { /* ignore */ }
    }
  }

  S.init = function () {
    handleLogoutParam();
    applyHeader();
    cookieBanner();
  };

  w.SHB = S;
  if (d.readyState === 'loading') {
    d.addEventListener('DOMContentLoaded', S.init);
  } else {
    S.init();
  }
})(window, document);
