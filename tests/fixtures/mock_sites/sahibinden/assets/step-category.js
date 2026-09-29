/* sahibinden.com mock - posting step 1: "Kategori Seçimi" multi-column browser */
(function (w, d) {
  'use strict';
  var S = w.SHB, D = w.SHB_DATA;
  if (!S.requireLogin()) { return; }

  var cols = d.getElementById('categoryColumns');
  var result = d.getElementById('categoryResult');
  var resultPath = d.getElementById('categoryResultPath');
  var btn = d.getElementById('btnCategoryContinue');
  var path = [];
  var token = 0;
  var LOAD_DELAY = 300;

  function scrollColumnsEnd() { cols.scrollLeft = cols.scrollWidth; }

  function setComplete(done) {
    result.hidden = !done;
    btn.disabled = !done;
    resultPath.textContent = done ? path.join(' > ') : '';
  }

  function removeColumnsAfter(level) {
    while (cols.children.length > level + 1) { cols.removeChild(cols.lastChild); }
  }

  function renderColumn(level, parentPath) {
    var children = D.childrenOf(parentPath);
    var col = d.createElement('div');
    col.className = 'category-column';
    var ul = d.createElement('ul');
    Object.keys(children).forEach(function (name) {
      var li = d.createElement('li');
      li.className = children[name] === null ? 'leaf' : 'has-child';
      var a = d.createElement('a');
      a.href = '#';
      a.textContent = name;
      a.title = name;
      a.addEventListener('click', function (e) {
        e.preventDefault();
        select(level, name, li);
      });
      li.appendChild(a);
      ul.appendChild(li);
    });
    col.appendChild(ul);
    cols.appendChild(col);
    return col;
  }

  function markSelected(li) {
    Array.prototype.forEach.call(li.parentNode.children, function (x) { x.classList.remove('selected'); });
    li.classList.add('selected');
  }

  function select(level, name, li) {
    var my = ++token;
    path = path.slice(0, level);
    path.push(name);
    markSelected(li);
    removeColumnsAfter(level);
    setComplete(false);
    var children = D.childrenOf(path);
    if (children === null) {
      w.setTimeout(function () {
        if (my !== token) { return; }
        setComplete(true);
      }, 150);
      return;
    }
    var loading = d.createElement('div');
    loading.className = 'category-column loading';
    loading.innerHTML = '<span class="spinner"></span>Yükleniyor...';
    cols.appendChild(loading);
    scrollColumnsEnd();
    var snapshot = path.slice();
    w.setTimeout(function () {
      if (my !== token) { return; }
      loading.remove();
      renderColumn(level + 1, snapshot);
      scrollColumnsEnd();
    }, LOAD_DELAY);
  }

  function restore(p) {
    path = [];
    for (var i = 0; i < p.length; i++) {
      var col = renderColumn(i, p.slice(0, i));
      var lis = col.querySelectorAll('li');
      for (var j = 0; j < lis.length; j++) {
        if (lis[j].textContent === p[i]) { markSelected(lis[j]); }
      }
      path.push(p[i]);
    }
    setComplete(true);
    scrollColumnsEnd();
  }

  btn.addEventListener('click', function () {
    if (!D.isLeafPath(path)) { return; }
    var draft = S.getDraft();
    var old = JSON.stringify(draft.category_path || []);
    if (old !== JSON.stringify(path)) {
      draft.category_path = path.slice();
      draft.attributes = {};
      draft.details_completed = false;
      draft.previewed = false;
    }
    S.saveDraft(draft);
    w.location.href = 'ilan-ver-detay.html';
  });

  var existing = S.getDraft().category_path;
  if (existing && D.isLeafPath(existing)) {
    restore(existing);
  } else {
    renderColumn(0, []);
    setComplete(false);
  }
})(window, document);
