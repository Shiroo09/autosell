/* sahibinden.com mock - search results page (arama.html)
   Rows are server-rendered in the HTML. pagingOffset=20 swaps in page 2 rows,
   sorting=price_asc|price_desc re-orders the rows client side. */
(function (w, d) {
  'use strict';
  var S = w.SHB;
  var params = S.params();
  var query = (params.get('query_text') || '').trim();
  var offset = parseInt(params.get('pagingOffset') || '0', 10) || 0;
  var sorting = params.get('sorting') || '';
  var tbody = d.querySelector('#searchResultsTable > tbody');
  var page2 = d.getElementById('searchResultsPage2');
  var PAGE_SIZE = 20;

  function url(extra) {
    var p = new URLSearchParams();
    if (query) { p.set('query_text', query); }
    if (sorting && !(extra && extra.sorting === null)) { p.set('sorting', sorting); }
    Object.keys(extra || {}).forEach(function (k) {
      if (extra[k] === null) { p.delete(k); } else { p.set(k, extra[k]); }
    });
    var s = p.toString();
    return 'arama.html' + (s ? '?' + s : '');
  }

  var qEl = d.getElementById('searchQueryText');
  var textEl = d.getElementById('resultText');
  if (query) { qEl.textContent = query; } else { textEl.innerHTML = 'Arama sonuçları: <span id="resultCount">33</span> ilan bulundu.'; }

  if (offset >= PAGE_SIZE && page2) {
    tbody.innerHTML = page2.innerHTML;
  }

  /* sort links keep the current query */
  d.querySelectorAll('a.sort-link').forEach(function (a) {
    var m = /sorting=([a-z_]+)/.exec(a.getAttribute('href'));
    if (m) { a.setAttribute('href', url({ sorting: m[1], pagingOffset: null })); }
    if (m && m[1] === sorting) { a.classList.add('active-sort'); }
  });

  /* pagination */
  var nav = d.getElementById('pageNavi');
  if (nav) {
    var html;
    if (offset >= PAGE_SIZE) {
      html = '<li><a class="prevNextBut" href="' + url({ pagingOffset: null }) + '" title="Önceki">Önceki</a></li>' +
        '<li><a href="' + url({ pagingOffset: null }) + '">1</a></li>' +
        '<li><span class="current">2</span></li>';
    } else {
      html = '<li><span class="current">1</span></li>' +
        '<li><a href="' + url({ pagingOffset: '20' }) + '">2</a></li>' +
        '<li><a class="prevNextBut" href="' + url({ pagingOffset: '20' }) + '" title="Sonraki Sayfa">Sonraki</a></li>';
    }
    nav.innerHTML = html;
  }

  /* client side sorting by price */
  if (sorting === 'price_asc' || sorting === 'price_desc') {
    var all = Array.prototype.slice.call(tbody.children);
    var fixed = [];
    var items = [];
    all.forEach(function (tr, i) {
      if (tr.hasAttribute('data-id')) { items.push(tr); } else { fixed.push([i, tr]); }
    });
    var price = function (tr) {
      var td = tr.querySelector('.searchResultsPriceValue');
      return Number(S.digits(td ? td.textContent : '0')) || 0;
    };
    items.sort(function (a, b) { return sorting === 'price_asc' ? price(a) - price(b) : price(b) - price(a); });
    fixed.forEach(function (f) { items.splice(Math.min(f[0], items.length), 0, f[1]); });
    items.forEach(function (tr) { tbody.appendChild(tr); });
  }
})(window, document);
