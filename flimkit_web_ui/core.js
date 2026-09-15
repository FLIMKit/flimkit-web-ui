'use strict';
var $ = function (id) { return document.getElementById(id); };
var S = null;
var App = { hooks: [], last: {}, imgIndex: 0, expertDirty: false };

function vis(el, on) { (typeof el === 'string' ? $(el) : el).hidden = !on; }

function toast(level, text) {
  var el = document.createElement('div');
  el.className = 'toast ' + level;
  el.textContent = text;
  $('toasts').appendChild(el);
  setTimeout(function () { el.remove(); }, level === 'error' ? 10000 : 6000);
}

function showNotes(list) {
  (list || []).forEach(function (n) { toast(n.level, (n.title ? n.title + ': ' : '') + n.message); });
}

function handleOut(out) {
  showNotes(out.notes);
  if (out.message) { toast('info', out.message); }
  if (out.ok === false) { toast('error', out.error || 'failed'); }
  if (out.download) { download(out.download); }
}

function post(url, body) {
  return fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(function (r) { return r.json(); })
    .catch(function () { return { ok: false, error: 'lost connection to FLIMKit' }; });
}

function act(name, args) {
  return post('/api/action', { name: name, args: args || {} }).then(function (out) { handleOut(out); poll(); return out; });
}

function setFields(obj) {
  return post('/api/set', obj).then(function (out) { handleOut(out); poll(); return out; });
}

function setField(key, value) { var o = {}; o[key] = value; return setFields(o); }

function download(d) {
  var url = URL.createObjectURL(new Blob([d.text], { type: d.mime }));
  var a = document.createElement('a');
  a.href = url; a.download = d.name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
}

function changed(key, value) {
  var s = JSON.stringify(value);
  if (App.last[key] === s) { return false; }
  App.last[key] = s;
  return true;
}

function fillTable(tbody, rows) {
  tbody.innerHTML = '';
  rows.forEach(function (row) {
    var tr = document.createElement('tr');
    row.forEach(function (v) { var td = document.createElement('td'); td.textContent = v; tr.appendChild(td); });
    tbody.appendChild(tr);
  });
}

/* ---------- figures rendered by the desktop app ---------- */

function Fig(key, img, canvas, onReady) {
  var f = { key: key, rev: -1, busy: false, geom: {} };
  f.update = function (rev) {
    if (rev === undefined || rev === f.rev || f.busy) { return; }
    f.busy = true;
    fetch('/api/fig.png?key=' + key).then(function (r) {
      if (!r.ok) { throw new Error('fig ' + r.status); }
      f.geom = JSON.parse(r.headers.get('X-Geom') || '{}');
      f.rev = parseInt(r.headers.get('X-Rev'), 10);
      return r.blob();
    }).then(function (blob) {
      var old = img.src;
      img.onload = function () {
        if (old && old.indexOf('blob:') === 0) { URL.revokeObjectURL(old); }
        f.busy = false;
        f.fit();
        if (onReady) { onReady(); }
      };
      img.src = URL.createObjectURL(blob);
    }).catch(function () { f.busy = false; });
  };
  f.fit = function () {
    if (!canvas) { return; }
    canvas.width = img.clientWidth;
    canvas.height = img.clientHeight;
  };
  f.toData = function (e, axName) {
    var r = canvas.getBoundingClientRect();
    var fx = (e.clientX - r.left) / r.width;
    var fy = 1 - (e.clientY - r.top) / r.height;
    var names = axName ? [axName] : Object.keys(f.geom);
    for (var i = 0; i < names.length; i++) {
      var g = f.geom[names[i]];
      if (!g) { continue; }
      var inside = fx >= g.x0 && fx <= g.x0 + g.w && fy >= g.y0 && fy <= g.y0 + g.h;
      if (!inside && !axName) { continue; }
      var ux = Math.min(Math.max((fx - g.x0) / g.w, 0), 1);
      var uy = Math.min(Math.max((fy - g.y0) / g.h, 0), 1);
      return { ax: names[i], inside: inside, px: [e.clientX - r.left, e.clientY - r.top],
               data: [g.xlim[0] + ux * (g.xlim[1] - g.xlim[0]), g.ylim[0] + uy * (g.ylim[1] - g.ylim[0])] };
    }
    return null;
  };
  f.toPx = function (axName, x, y) {
    var g = f.geom[axName];
    if (!g) { return null; }
    var ux = (x - g.xlim[0]) / (g.xlim[1] - g.xlim[0]);
    var uy = (y - g.ylim[0]) / (g.ylim[1] - g.ylim[0]);
    return [(g.x0 + ux * g.w) * canvas.width, (1 - (g.y0 + uy * g.h)) * canvas.height];
  };
  window.addEventListener('resize', function () { f.fit(); if (onReady) { onReady(); } });
  return f;
}

/* ---------- form fields ---------- */

document.addEventListener('change', function (e) {
  var el = e.target;
  var key = el.dataset && el.dataset.field;
  if (!key) { return; }
  if (el.type === 'checkbox') { setField(key, el.checked); }
  else if (el.type === 'radio') { if (el.checked) { setField(key, el.value); } }
  else { setField(key, el.value); }
});

function testCond(expr) {
  return expr.split('&').every(function (part) {
    var neg = part.indexOf('!=') >= 0;
    var bits = part.split(neg ? '!=' : '=');
    var v = S ? String(S.fields[bits[0].trim()]) : '';
    var hit = bits[1].split('|').indexOf(v) >= 0;
    return neg ? !hit : hit;
  });
}

function buildChoices() {
  if (!changed('choices', S.choices)) { return; }
  document.querySelectorAll('[data-irf]').forEach(function (box) {
    box.innerHTML = '';
    S.choices.irf.forEach(function (c) {
      var lab = document.createElement('label');
      var inp = document.createElement('input');
      inp.type = 'radio'; inp.name = box.dataset.irf + '.method'; inp.value = c[1]; inp.dataset.field = box.dataset.irf + '.method';
      lab.appendChild(inp);
      lab.appendChild(document.createTextNode(' ' + c[0]));
      box.appendChild(lab);
    });
  });
  document.querySelectorAll('[data-choices=cmap]').forEach(function (sel) {
    sel.innerHTML = '';
    S.choices.cmap.forEach(function (c) { sel.add(new Option(c, c)); });
  });
}

function applyFields() {
  document.querySelectorAll('[data-field]').forEach(function (el) {
    var key = el.dataset.field;
    if (!(key in S.fields)) { return; }
    var v = S.fields[key];
    if (el.type === 'checkbox') { el.checked = v === true; }
    else if (el.type === 'radio') { el.checked = String(v) === el.value; }
    else if (document.activeElement !== el) { el.value = v; }
  });
  document.querySelectorAll('[data-when]').forEach(function (el) { vis(el, testCond(el.dataset.when)); });
  document.querySelectorAll('[data-enable]').forEach(function (el) { el.disabled = !testCond(el.dataset.enable); });
  document.querySelectorAll('[data-forms]').forEach(function (el) { vis(el, el.dataset.forms.split(' ').indexOf(S.form) >= 0); });
  document.querySelectorAll('[data-form]').forEach(function (b) { b.classList.toggle('on', b.dataset.form === S.form); });
}

document.querySelectorAll('[data-form]').forEach(function (b) {
  b.addEventListener('click', function () { act('switch_form', { form: b.dataset.form }); });
});

/* ---------- run / progress ---------- */

var RUN = { fov: 'run_fov', stitch: 'run_stitch', batch: 'run_batch', irf: 'run_irf', phasor: 'run_phasor' };

document.querySelectorAll('[data-run]').forEach(function (b) {
  b.addEventListener('click', function () {
    var form = b.dataset.run;
    selectTab('tab-log');
    var args = form === 'phasor' ? { channel: $('ph-channel').value, frequency: $('ph-freq').value } : {};
    act(RUN[form], args);
  });
});
$('btn-cancel').addEventListener('click', function () { act('cancel'); });

function applyRun() {
  document.querySelectorAll('[data-run]').forEach(function (b) {
    var form = b.dataset.run;
    b.textContent = S.run_labels[form];
    b.disabled = form === 'phasor' ? S.busy.phasor : S.running;
  });
  $('btn-cancel').disabled = S.progress.length === 0;
  $('results-status').textContent = S.results_status;
  vis('expert-badge', S.expert_active);
  var box = $('progress');
  box.innerHTML = '';
  S.progress.forEach(function (p) {
    var row = document.createElement('div');
    row.className = 'row';
    var pct = p.maximum > 0 ? Math.round(100 * p.value / p.maximum) : 0;
    row.innerHTML = '<span></span><div class="bar"><div style="width:' + pct + '%"></div></div><span class="muted"></span>';
    row.children[0].textContent = p.task;
    row.children[2].textContent = p.status;
    box.appendChild(row);
  });
}

/* ---------- polling ---------- */

function poll() {
  return fetch('/api/state').then(function (r) { return r.json(); }).then(function (s) {
    if (s.ok === false) { showNotes(s.notes); $('conn').textContent = s.error; return; }
    S = s;
    $('conn').textContent = '';
    showNotes(s.notes);
    buildChoices();
    applyFields();
    applyRun();
    applyResults();
    applyExpert();
    App.hooks.forEach(function (h) { try { h(s); } catch (err) { console.error(err); } });
  }).catch(function () { $('conn').textContent = 'lost connection to FLIMKit'; });
}

function loop() { poll().then(function () { setTimeout(loop, 1000); }); }

/* ---------- results ---------- */

function selectTab(id) {
  document.querySelectorAll('[data-tab]').forEach(function (b) {
    b.classList.toggle('on', b.dataset.tab === id);
    vis(b.dataset.tab, b.dataset.tab === id);
  });
}
document.querySelectorAll('[data-tab]').forEach(function (b) { b.addEventListener('click', function () { selectTab(b.dataset.tab); }); });

function applyResults() {
  if (S.log_len !== App.last.logLen) {
    App.last.logLen = S.log_len;
    var log = $('log');
    var atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 20;
    log.textContent = S.log_tail;
    if (atBottom) { log.scrollTop = log.scrollHeight; }
  }
  if (changed('summary', S.summary)) {
    fillTable($('summary-body'), S.summary);
    if (S.summary.length) { selectTab('tab-summary'); }
  }
  if (changed('export-keys', S.export_images)) {
    var box = $('export-keys');
    box.innerHTML = S.export_images.length ? '' : '<span class="muted">No fit images available to export.</span>';
    S.export_images.forEach(function (k) {
      var lab = document.createElement('label');
      var cb = document.createElement('input');
      cb.type = 'checkbox'; cb.checked = true; cb.value = k;
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(' ' + k.replace(/_/g, ' ')));
      box.appendChild(lab);
    });
  }
  if (changed('output-dir', S.output_dir) && document.activeElement !== $('export-path')) { $('export-path').value = S.output_dir; }
  if (changed('images', S.images)) {
    App.imgIndex = 0;
    $('img-slider').max = Math.max(S.images.length - 1, 0);
    drawResultImage();
    if (S.images.length) { selectTab('tab-images'); }
  }
}

function drawResultImage() {
  var imgs = S ? S.images : [];
  if (!imgs.length) { $('result-img').removeAttribute('src'); $('result-label').textContent = 'No images found'; return; }
  App.imgIndex = Math.max(0, Math.min(App.imgIndex, imgs.length - 1));
  $('img-slider').value = App.imgIndex;
  $('result-img').src = '/api/result_image?i=' + App.imgIndex + '&p=' + encodeURIComponent(imgs[App.imgIndex]);
  $('result-label').textContent = imgs[App.imgIndex].split(/[\\/]/).pop() + '  (' + (App.imgIndex + 1) + '/' + imgs.length + ')';
}

$('img-prev').addEventListener('click', function () { App.imgIndex -= 1; drawResultImage(); });
$('img-next').addEventListener('click', function () { App.imgIndex += 1; drawResultImage(); });
$('img-slider').addEventListener('input', function () { App.imgIndex = parseInt($('img-slider').value, 10); drawResultImage(); });
$('save-log').addEventListener('click', function () { act('save_log'); });
$('clear-log').addEventListener('click', function () { act('clear_log'); });
$('summary-csv').addEventListener('click', function () { act('export_summary_csv'); });
$('export-all').addEventListener('click', function () { document.querySelectorAll('#export-keys input').forEach(function (el) { el.checked = true; }); });
$('export-none').addEventListener('click', function () { document.querySelectorAll('#export-keys input').forEach(function (el) { el.checked = false; }); });
$('export-go').addEventListener('click', function () {
  var keys = Array.prototype.map.call(document.querySelectorAll('#export-keys input:checked'), function (el) { return el.value; });
  act('export_images', { images: keys, scalebar: $('export-scalebar').checked, annotations: $('export-annotations').checked,
                         format: document.querySelector('input[name=export-format]:checked').value, path: $('export-path').value });
});
$('load-session').addEventListener('click', function () { act('load_session', { path: $('load-session-path').value }); });
$('save-session').addEventListener('click', function () { act('save_session', { path: $('save-session-path').value }); });
$('save-as').addEventListener('click', function () { act('save_npz_as', { path: $('save-as-path').value }); });
$('menu-reset').addEventListener('click', function () { if (confirm('Clear all regions and results? This cannot be undone.')) { act('menu_reset'); } });

/* ---------- expert settings ---------- */

function applyExpert() {
  if (App.expertDirty) { return; }
  document.querySelectorAll('[data-expert]').forEach(function (el) {
    var v = S.expert[el.dataset.expert];
    if (el.type === 'checkbox') { el.checked = v === true; }
    else if (document.activeElement !== el) { el.value = v === null || v === undefined ? '' : v; }
  });
}
document.querySelectorAll('[data-expert]').forEach(function (el) {
  el.addEventListener('input', function () { App.expertDirty = true; });
  el.addEventListener('change', function () { App.expertDirty = true; });
});
$('expert-save').addEventListener('click', function () {
  var values = {};
  document.querySelectorAll('[data-expert]').forEach(function (el) { values[el.dataset.expert] = el.type === 'checkbox' ? el.checked : el.value; });
  act('expert_save', { values: values }).then(function (out) { if (out.ok) { App.expertDirty = false; toast('info', 'Expert settings saved'); } });
});
$('expert-reset').addEventListener('click', function () { App.expertDirty = false; act('expert_reset'); });

/* ---------- file picker ---------- */

var picker = { kind: 'file', cb: null, dir: '~', parent: null };

function openPicker(kind, start, cb) {
  picker.kind = kind;
  picker.cb = cb;
  $('picker-title').textContent = kind === 'dir' ? 'Choose a folder' : 'Choose a file';
  vis('picker-this', kind === 'dir');
  vis('picker', true);
  var dir = start || picker.dir;
  if (kind === 'file' && start) { dir = start.replace(/[\\/][^\\/]*$/, ''); }
  browse(dir || '~');
}

function browse(dir) {
  fetch('/api/browse?dir=' + encodeURIComponent(dir)).then(function (r) { return r.json(); }).then(function (d) {
    if (d.error) { toast('error', d.error); return; }
    picker.dir = d.dir;
    picker.parent = d.parent;
    $('picker-dir').textContent = d.dir;
    var ul = $('picker-list');
    ul.innerHTML = '';
    d.entries.forEach(function (e) {
      var li = document.createElement('li');
      li.className = e.is_dir ? 'dir' : (picker.kind === 'dir' ? 'dim' : 'file');
      li.textContent = (e.is_dir ? '▸ ' : '') + e.name;
      li.addEventListener('click', function () {
        if (e.is_dir) { browse(e.path); } else if (picker.kind === 'file') { closePicker(e.path); }
      });
      ul.appendChild(li);
    });
  });
}

function closePicker(path) {
  vis('picker', false);
  if (path && picker.cb) { picker.cb(path); }
}

$('picker-up').addEventListener('click', function () { if (picker.parent) { browse(picker.parent); } });
$('picker-this').addEventListener('click', function () { closePicker(picker.dir); });
$('picker-cancel').addEventListener('click', function () { closePicker(null); });

document.addEventListener('click', function (e) {
  var b = e.target.closest && e.target.closest('[data-pick],[data-pick-target]');
  if (!b) { return; }
  if (b.dataset.pick) {
    var key = b.dataset.pick;
    openPicker(b.dataset.kind, S ? String(S.fields[key] || '') : '', function (path) { setField(key, path); });
  } else {
    var input = $(b.dataset.pickTarget);
    var suffix = b.dataset.pickSuffix || '';
    openPicker(b.dataset.kind, input.value.replace(suffix, ''), function (path) { input.value = path + suffix; });
  }
});

/* ---------- modal ---------- */

function openModal(title, node) {
  $('modal-title').textContent = title;
  var body = $('modal-body');
  body.innerHTML = '';
  if (typeof node === 'string') { body.innerHTML = node; } else { body.appendChild(node); }
  vis('modal', true);
  return body;
}
function closeModal() { vis('modal', false); App.modalTool = null; }
$('modal-close').addEventListener('click', closeModal);

function showFitResult(prefix, out, src, ids) {
  $(prefix + '-fit-img').src = '/api/fit.png?src=' + src + '&ids=' + (ids || []).join(',') + '&t=' + Date.now();
  $(prefix + '-fit-name').textContent = out.name + '  (IRF: ' + out.irf_source + ')';
  fillTable($(prefix + '-fit-rows'), out.rows);
  vis(prefix + '-result', true);
}

document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape' && !$('picker').hidden) { closePicker(null); }
  else if (e.key === 'Escape' && !$('modal').hidden) { closeModal(); }
});
