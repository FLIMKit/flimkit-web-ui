'use strict';

/* ---------- batch + machine IRF ---------- */

(function () {
  var irfFig = Fig('irf', $('irf-img'), null, null);
  App.hooks.push(function (s) {
    $('batch-beside').textContent = '→ ' + s.batch.beside;
    $('batch-help').textContent = s.batch.help;
    var hasIrf = s.figs.irf !== undefined;
    vis('irf-img', hasIrf);
    vis('irf-empty', !hasIrf);
    if (s.form === 'irf' && hasIrf) { irfFig.update(s.figs.irf); }
  });
})();

/* ---------- phasor ---------- */

(function () {
  var poly = null;
  var drag = null;
  var pendingFit = false;
  var fig = Fig('phasor', $('ph-img'), $('ph-overlay'), function () { draw(); });

  function cursors() { return S ? S.phasor.cursors : []; }

  function anchor(c) {
    if (c.type === 'ellipse') { return [c.g, c.s]; }
    var g = 0, s = 0;
    c.vertices.forEach(function (v) { g += v[0]; s += v[1]; });
    return [g / c.vertices.length, s / c.vertices.length];
  }

  function inPoly(pt, vs) {
    var inside = false;
    for (var i = 0, j = vs.length - 1; i < vs.length; j = i++) {
      var xi = vs[i][0], yi = vs[i][1], xj = vs[j][0], yj = vs[j][1];
      if (((yi > pt[1]) !== (yj > pt[1])) && (pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi) + xi)) { inside = !inside; }
    }
    return inside;
  }

  function hitTest(pt) {
    var r = parseFloat(S.fields['ph.radius']) || 0.05;
    var list = cursors();
    for (var i = 0; i < list.length; i++) {
      var c = list[i];
      if (c.type === 'poly') { if (inPoly(pt, c.vertices)) { return i; } }
      else if (Math.hypot(pt[0] - c.g, pt[1] - c.s) < Math.max(r * 1.2, 0.04)) { return i; }
    }
    return -1;
  }

  function draw() {
    var c = $('ph-overlay');
    var ctx = c.getContext('2d');
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.lineWidth = 1.5;
    if (poly && poly.px.length) {
      ctx.strokeStyle = 'cyan';
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      ctx.moveTo(poly.px[0][0], poly.px[0][1]);
      poly.px.forEach(function (p) { ctx.lineTo(p[0], p[1]); });
      if (poly.hover) { ctx.lineTo(poly.hover[0], poly.hover[1]); }
      ctx.stroke();
      ctx.setLineDash([]);
      poly.px.forEach(function (p) { ctx.fillStyle = 'cyan'; ctx.fillRect(p[0] - 2, p[1] - 2, 4, 4); });
    }
    if (drag && drag.cur) {
      var a = fig.toPx('ph', drag.start[0], drag.start[1]);
      var b = fig.toPx('ph', drag.cur[0], drag.cur[1]);
      ctx.strokeStyle = cursors()[drag.i] ? cursors()[drag.i].color : 'white';
      ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke();
      ctx.beginPath(); ctx.arc(b[0], b[1], 6, 0, 2 * Math.PI); ctx.stroke();
    }
  }

  function finishPoly() {
    var p = poly;
    poly = null;
    draw();
    if (p && p.data.length >= 3) { act('ph_add_poly', { vertices: p.data }); }
    else if (p) { toast('warning', 'A polygon needs at least 3 vertices.'); }
  }

  var ov = $('ph-overlay');
  ov.addEventListener('mousedown', function (e) {
    if (e.button !== 0 || !S || !S.phasor.loaded) { return; }
    var h = fig.toData(e, 'ph');
    if (!h || (!h.inside && !poly)) { return; }
    if (poly) { poly.data.push(h.data); poly.px.push(h.px); draw(); return; }
    var hit = hitTest(h.data);
    if (hit >= 0) { drag = { i: hit, start: h.data, cur: null }; return; }
    if (S.fields['ph.mode'] === 'poly') { poly = { data: [h.data], px: [h.px] }; draw(); }
    else { act('ph_add_ellipse', { g: h.data[0], s: h.data[1] }); }
  });
  ov.addEventListener('mousemove', function (e) {
    var h = fig.toData(e, 'ph');
    if (!h) { return; }
    if (drag) { drag.cur = h.data; draw(); return; }
    if (poly) { poly.hover = h.px; draw(); return; }
    ov.style.cursor = S && S.phasor.loaded && h.inside && hitTest(h.data) >= 0 ? 'move' : 'crosshair';
  });
  ov.addEventListener('mouseup', function () {
    if (!drag) { return; }
    var d = drag;
    drag = null;
    draw();
    if (!d.cur || Math.hypot(d.cur[0] - d.start[0], d.cur[1] - d.start[1]) < 1e-4) { return; }
    var base = anchor(cursors()[d.i]);
    act('ph_move', { i: d.i, g: base[0] + d.cur[0] - d.start[0], s: base[1] + d.cur[1] - d.start[1] });
  });
  ov.addEventListener('dblclick', function () { if (poly) { finishPoly(); } });
  ov.addEventListener('contextmenu', function (e) { if (poly) { e.preventDefault(); finishPoly(); } });
  document.addEventListener('keydown', function (e) {
    if (!poly) { return; }
    if (e.key === 'Enter') { finishPoly(); }
    else if (e.key === 'Escape') { poly = null; draw(); }
  });

  App.hooks.push(function (s) {
    if (s.form !== 'phasor') { return; }
    fig.update(s.figs.phasor);
    $('ph-status').textContent = s.phasor.status;
    $('ph-radius-val').textContent = Number(s.fields['ph.radius']).toFixed(3);
    $('ph-ratio-val').textContent = Number(s.fields['ph.ratio']).toFixed(2);
    $('ph-hint').textContent = !s.phasor.loaded ? '' : (s.fields['ph.mode'] === 'poly'
      ? 'Click to add vertices; double-click, right-click or Enter closes (Esc cancels). Drag a cursor to move it.'
      : 'Click the phasor plot to place a cursor (' + s.phasor.cursors.length + '/' + s.phasor.max_cursors + '). Drag a cursor to move it.');
    if (changed('ph-peaks', s.phasor.peaks)) {
      var box = $('ph-peaks-list');
      box.innerHTML = '<span class="muted">Peaks:</span>';
      s.phasor.peaks.forEach(function (p) {
        var b = document.createElement('button');
        b.textContent = '+ cursor at ' + p.tau.toFixed(2) + ' ns';
        b.addEventListener('click', function () { act('ph_add_ellipse', { g: p.g, s: p.s }); });
        box.appendChild(b);
      });
      vis(box, s.phasor.peaks.length > 0);
    }
    if (pendingFit && !s.running && s.phasor.has_fit) { pendingFit = false; viewFit(true); }
  });

  function viewFit(quiet) {
    post('/api/action', { name: 'fit_rows', args: { src: 'phasor' } }).then(function (out) {
      if (out.ok === false) { if (!quiet) { toast('warning', out.error); } return; }
      showFitResult('ph', out, 'phasor', []);
    });
  }

  $('ph-clear').addEventListener('click', function () { poly = null; draw(); act('ph_clear'); });
  $('ph-undo').addEventListener('click', function () {
    if (poly && poly.data.length) { poly.data.pop(); poly.px.pop(); if (!poly.data.length) { poly = null; } draw(); return; }
    act('ph_undo');
  });
  $('ph-filter-apply').addEventListener('click', function () {
    var f = {};
    document.querySelectorAll('[data-field^="ph.filter_"]').forEach(function (el) { f[el.dataset.field] = el.value; });
    post('/api/set', f).then(function () { act('ph_filter_apply'); });
  });
  $('ph-filter-reset').addEventListener('click', function () { act('ph_filter_reset'); });
  $('ph-peaks').addEventListener('click', function () { act('ph_find_peaks'); });
  $('ph-fret-overlay').addEventListener('click', function () { act('ph_fret_overlay'); });
  $('ph-fret-fit').addEventListener('click', function () { act('ph_fit_fret'); });
  $('ph-fret-clear').addEventListener('click', function () { act('ph_clear_overlay'); });
  $('ph-fit').addEventListener('click', function () {
    act('ph_fit_decay', { n_exp: parseInt($('ph-nexp').value, 10), tau_min: $('ph-tmin').value,
                          tau_max: $('ph-tmax').value, cost_function: $('ph-cost').value })
      .then(function (out) { if (out.ok) { pendingFit = true; } });
  });
  $('ph-view').addEventListener('click', function () { viewFit(false); });
  $('ph-save').addEventListener('click', function () { act('ph_save_session', { path: $('ph-save-path').value }); });
})();

/* ---------- tools menu ---------- */

(function () {
  function el(tag, attrs, text) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    if (text !== undefined) { e.textContent = text; }
    return e;
  }

  function row() { var r = el('div', { class: 'row' }); Array.prototype.slice.call(arguments).forEach(function (c) { r.appendChild(c); }); return r; }

  function button(text, fn) { var b = el('button', {}, text); b.addEventListener('click', fn); return b; }

  function pickButton(input, kind) {
    return button('Browse...', function () { openPicker(kind, input.value, function (p) { input.value = p; }); });
  }

  var tools = {};

  tools.project = function () {
    var box = el('div');
    var path = el('input', { type: 'text', class: 'grow', placeholder: 'project folder' });
    box.appendChild(row(path, pickButton(path, 'dir'), button('Open Project Folder', function () { act('open_project', { path: path.value }); })));
    box.appendChild(el('div', { class: 'muted', id: 'proj-status' }));
    box.appendChild(el('ul', { class: 'list', id: 'proj-list' }));
    box.appendChild(el('div', { class: 'muted' }, '● fit session  ◐ phasor session  ◉ both  ○ none  |  F single FOV  T tiles  Z z-stack'));
    box.appendChild(el('div', { class: 'h2', style: 'margin-top:10px' }, 'Recent Files'));
    box.appendChild(el('ul', { class: 'list', id: 'recent-list' }));
    box.appendChild(row(button('Clear Recent', function () { act('recent_clear'); })));
    openModal('Project', box);
    App.last.project = null;
    App.last.recent = null;
    refreshProject(S);
  };

  function refreshProject(s) {
    if (App.modalTool !== 'project' || !s) { return; }
    $('proj-status').textContent = s.project.status;
    if (changed('project', s.project)) {
      var ul = $('proj-list');
      ul.innerHTML = '';
      s.project.items.forEach(function (label, i) {
        var li = el('li', { class: 'mono' + (s.project.selected.indexOf(i) >= 0 ? ' sel' : '') }, label);
        li.addEventListener('click', function () { act('project_select', { i: i }); });
        ul.appendChild(li);
      });
    }
    if (changed('recent', s.recent)) {
      var rl = $('recent-list');
      rl.innerHTML = '';
      if (!s.recent.length) { rl.appendChild(el('li', { class: 'dim' }, '(No recent items)')); }
      s.recent.forEach(function (entry, i) {
        var li = el('li', { class: 'mono' }, (entry.type === 'project' ? '[Project] ' : '') + entry.path);
        li.addEventListener('click', function () { act('recent_open', { i: i }); });
        rl.appendChild(li);
      });
    }
  }
  App.hooks.push(refreshProject);

  var SYNTH = [
    ['Lifetime(s) τ, ns (comma for multi-exp)', 'tau', '4.1'], ['Amplitudes (comma, blank = equal)', 'amps', ''],
    ['Photons (comma = a series)', 'photons', '1e5'], ['Laser period, ns', 'period', '50'],
    ['TCSPC bin width, ps', 'res', '25'], ['IRF FWHM, ns', 'irf_fwhm', '0.15'], ['IRF centre, ns', 'irf_center', '2.0'],
    ['Reflection at, ns (blank = none)', 'refl_ns', ''], ['Reflection fraction', 'refl_frac', '0.02'],
    ['Pile-up, photons/pulse (blank = none)', 'pileup', ''], ['Image side, px', 'image', '16'], ['Base name', 'name', 'synth'],
  ];

  tools.synth = function () {
    var box = el('div');
    var inputs = {};
    SYNTH.forEach(function (f) {
      var inp = el('input', { type: 'text' });
      inp.value = f[2];
      inputs[f[1]] = inp;
      var lab = el('label', { class: 'lbl' }, f[0]);
      lab.style.minWidth = '260px';
      box.appendChild(row(lab, inp));
    });
    var sdt = el('input', { type: 'checkbox' });
    var sdtLab = el('label');
    sdtLab.appendChild(sdt);
    sdtLab.appendChild(document.createTextNode(' Also write Becker & Hickl .sdt'));
    box.appendChild(row(sdtLab));
    var out = el('input', { type: 'text', class: 'grow', placeholder: 'output folder for the PTUs' });
    box.appendChild(row(out, pickButton(out, 'dir')));
    var go = button('Generate', function () {
      var values = {};
      Object.keys(inputs).forEach(function (k) { values[k] = inputs[k].value; });
      go.disabled = true;
      act('synth_generate', { values: values, out_dir: out.value, sdt: sdt.checked }).then(function (r) {
        go.disabled = false;
        if (r.ok) { closeModal(); }
      });
    });
    box.appendChild(row(go));
    openModal('Generate Synthetic PTU', box);
  };

  tools.prefs = function () {
    openModal('Preferences', '<div class="muted">Loading...</div>');
    act('prefs_get').then(function (out) {
      if (!out.ok) { return; }
      var p = out.prefs;
      var box = el('div');
      function sel(values, v) { var s = el('select'); values.forEach(function (x) { s.add(new Option(x, x)); }); s.value = v; return s; }
      function txt(v) { var i = el('input', { type: 'text' }); i.value = v; return i; }
      function chk(v, label) { var l = el('label'); var c = el('input', { type: 'checkbox' }); c.checked = v === true; l.appendChild(c); l.appendChild(document.createTextNode(' ' + label)); l.input = c; return l; }
      var cmap = sel(['viridis', 'plasma', 'gray', 'jet'], p.colormap);
      var font = txt(p.font_size);
      var nexp = txt(p.default_nexp);
      var fmt = sel(['CSV', 'Excel', 'NumPy'], p.export_format);
      var outdir = txt(p.output_directory);
      outdir.className = 'grow';
      var autosave = chk(p.auto_save_npz, 'Enable auto-save NPZ');
      var penabled = chk(p.plugins_enabled, 'Load plugins at startup');
      var puser = chk(p.user_plugins, 'Load from ' + p.user_dir);
      var dirs = el('textarea', { rows: '4', style: 'width:100%' });
      dirs.value = p.plugin_dirs;
      box.appendChild(el('div', { class: 'h2' }, 'Display'));
      box.appendChild(row(el('label', { class: 'lbl' }, 'Colormap'), cmap));
      box.appendChild(row(el('label', { class: 'lbl' }, 'Font size'), font));
      box.appendChild(el('div', { class: 'h2' }, 'Analysis'));
      box.appendChild(row(el('label', { class: 'lbl' }, 'Default exponents'), nexp));
      box.appendChild(row(el('label', { class: 'lbl' }, 'Export format'), fmt));
      box.appendChild(el('div', { class: 'h2' }, 'Files'));
      box.appendChild(row(el('label', { class: 'lbl' }, 'Output directory'), outdir, pickButton(outdir, 'dir')));
      box.appendChild(row(autosave));
      box.appendChild(el('div', { class: 'h2' }, 'Plugins'));
      box.appendChild(row(penabled));
      box.appendChild(row(puser));
      box.appendChild(el('div', { class: 'muted' }, 'Extra plugin folders, one per line:'));
      box.appendChild(dirs);
      box.appendChild(el('div', { class: 'muted' }, 'Plugin changes take effect on the next start.'));
      box.appendChild(row(button('Save', function () {
        act('prefs_save', { values: {
          colormap: cmap.value, font_size: font.value, default_nexp: nexp.value, export_format: fmt.value,
          output_directory: outdir.value, auto_save_npz: autosave.input.checked,
          plugins_enabled: penabled.input.checked, user_plugins: puser.input.checked, plugin_dirs: dirs.value,
        } }).then(function (r) { if (r.ok) { closeModal(); } });
      }), button('Cancel', closeModal)));
      openModal('Preferences', box);
      App.modalTool = 'prefs';
    });
  };

  tools.plugins = function () {
    openModal('Plugins', '<div class="muted">Loading...</div>');
    act('plugins_info').then(function (out) {
      if (!out.ok) { return; }
      var box = el('div');
      box.appendChild(el('pre', { style: 'max-height:260px' }, out.report));
      box.appendChild(el('div', { class: 'h2', style: 'margin-top:8px' }, 'Load on next start'));
      out.plugins.forEach(function (p) {
        var l = el('label');
        var c = el('input', { type: 'checkbox' });
        c.checked = p.enabled;
        c.addEventListener('change', function () { act('plugin_toggle', { name: p.name, enabled: c.checked }); });
        l.appendChild(c);
        l.appendChild(document.createTextNode(' ' + p.name));
        box.appendChild(row(l));
      });
      if (!out.user_plugins) {
        box.appendChild(row(button('Enable user plugins', function () {
          if (confirm('Every .py file in the user plugin folder will be imported at startup.\n\nA plugin is ordinary Python with the same access to your machine as FLIMKit itself. There is no sandbox. Only enable this for files you trust.\n\nEnable?')) {
            act('enable_user_plugins');
          }
        })));
      }
      openModal('Plugins', box);
      App.modalTool = 'plugins';
    });
  };

  tools.help = function () {
    var box = el('div');
    var pre = el('pre', { style: 'min-height:120px; max-height:420px' }, '');
    function show(name, waiting) {
      pre.textContent = waiting || 'Loading...';
      act(name).then(function (out) { if (out.ok) { pre.textContent = out.text; } else { pre.textContent = out.error; } });
    }
    box.appendChild(row(
      button('About', function () { show('about'); }),
      button('Check for Updates', function () { show('update_check', 'Checking git status and latest available release...'); }),
      button('View Error Logs', function () { show('error_logs'); }),
      button('Export Error Logs', function () { act('export_error_logs'); })
    ));
    box.appendChild(pre);
    openModal('Help', box);
    App.modalTool = 'help';
    show('about');
  };

  document.querySelectorAll('[data-tool]').forEach(function (b) {
    b.addEventListener('click', function () { App.modalTool = b.dataset.tool; tools[b.dataset.tool](); });
  });
})();

loop();
