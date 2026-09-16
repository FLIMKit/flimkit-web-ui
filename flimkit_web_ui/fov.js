'use strict';
(function () {
  var roiMode = 'select';
  var drawing = null;
  var pendingFit = null;
  var fig = Fig('fov', $('fov-img'), $('fov-overlay'), function () { sizeOverlay(); });

  var HINTS = {
    select: 'Tick rows in the table to select regions.',
    rect: 'Drag on the intensity or FLIM image to draw a rectangle.',
    ellipse: 'Drag on the image to draw an ellipse.',
    polygon: 'Click to add points; double-click or right-click to close (Esc cancels).',
    freehand: 'Hold and drag to draw a freehand outline.',
  };

  function sizeOverlay() {
    var c = $('fov-overlay');
    c.style.pointerEvents = roiMode === 'select' ? 'none' : 'auto';
    redraw();
  }

  function redraw() {
    var c = $('fov-overlay');
    var ctx = c.getContext('2d');
    ctx.clearRect(0, 0, c.width, c.height);
    if (!drawing || drawing.px.length === 0) { return; }
    ctx.strokeStyle = 'cyan';
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    var p = drawing.px;
    if (drawing.tool === 'rect' || drawing.tool === 'ellipse') {
      var a = p[0], b = p[p.length - 1];
      if (drawing.tool === 'rect') { ctx.rect(Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(b[0] - a[0]), Math.abs(b[1] - a[1])); }
      else { ctx.ellipse((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, Math.abs(b[0] - a[0]) / 2, Math.abs(b[1] - a[1]) / 2, 0, 0, 2 * Math.PI); }
    } else {
      ctx.moveTo(p[0][0], p[0][1]);
      for (var i = 1; i < p.length; i++) { ctx.lineTo(p[i][0], p[i][1]); }
      if (drawing.tool === 'polygon' && drawing.hover) { ctx.lineTo(drawing.hover[0], drawing.hover[1]); }
    }
    ctx.stroke();
  }

  function finish() {
    var d = drawing;
    drawing = null;
    redraw();
    if (!d) { return; }
    var box = d.tool === 'rect' || d.tool === 'ellipse';
    if (d.data.length < (box ? 2 : 3)) { return; }
    act('roi_add', { tool: d.tool, coords: box ? [d.data[0], d.data[d.data.length - 1]] : d.data });
  }

  var ov = $('fov-overlay');
  ov.addEventListener('mousedown', function (e) {
    if (e.button !== 0 || roiMode === 'select') { return; }
    if (roiMode === 'polygon') {
      var hit = fig.toData(e, drawing ? drawing.ax : null);
      if (!hit) { return; }
      if (!drawing) { drawing = { tool: 'polygon', ax: hit.ax, data: [], px: [] }; }
      drawing.data.push(hit.data);
      drawing.px.push(hit.px);
      redraw();
      return;
    }
    var h = fig.toData(e, null);
    if (!h) { return; }
    drawing = { tool: roiMode, ax: h.ax, data: [h.data], px: [h.px], down: true };
  });
  ov.addEventListener('mousemove', function (e) {
    if (!drawing) { return; }
    var h = fig.toData(e, drawing.ax);
    if (!h) { return; }
    if (drawing.tool === 'polygon') { drawing.hover = h.px; redraw(); return; }
    if (!drawing.down) { return; }
    if (drawing.tool === 'freehand') { drawing.data.push(h.data); drawing.px.push(h.px); }
    else { drawing.data[1] = h.data; drawing.px[1] = h.px; }
    redraw();
  });
  ov.addEventListener('mouseup', function () { if (drawing && drawing.tool !== 'polygon') { finish(); } });
  ov.addEventListener('dblclick', function () { if (drawing && drawing.tool === 'polygon') { finish(); } });
  ov.addEventListener('contextmenu', function (e) { if (drawing && drawing.tool === 'polygon') { e.preventDefault(); finish(); } });
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape' && drawing) { drawing = null; redraw(); } });

  document.querySelectorAll('#roi-modes [data-mode]').forEach(function (b) {
    b.addEventListener('click', function () {
      roiMode = b.dataset.mode;
      drawing = null;
      sizeOverlay();
      act('roi_mode', { mode: roiMode });
    });
  });

  function selectedIds() {
    return Array.prototype.map.call(document.querySelectorAll('#roi-body input:checked'), function (el) { return parseInt(el.value, 10); });
  }

  function viewFit(ids, quiet) {
    post('/api/action', { name: 'fit_rows', args: { src: 'roi', ids: ids } }).then(function (out) {
      if (out.ok === false) { if (!quiet) { toast('warning', out.error); } return; }
      showFitResult('roi', out, 'roi', ids);
    });
  }

  App.hooks.push(function (s) {
    if (s.form !== 'fov' && s.form !== 'stitch') { return; }
    fig.update(s.figs.fov);
    $('fov-status').textContent = s.preview_status;
    vis('scale', s.scale_controls);
    vis('row-z', !!s.z);
    if (s.z) {
      $('z-label').textContent = s.z.label;
      $('z').max = s.z.n - 1;
      if (document.activeElement !== $('z')) { $('z').value = s.z.i; }
    }
    document.querySelectorAll('#roi-modes [data-mode]').forEach(function (b) { b.classList.toggle('on', b.dataset.mode === roiMode); });
    $('roi-hint').textContent = HINTS[roiMode];
    $('roi-status').textContent = s.roi_status;
    if (changed('rois', [s.rois, s.roi_selected])) {
      var body = $('roi-body');
      body.innerHTML = '';
      s.rois.forEach(function (r) {
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        var cb = document.createElement('input');
        cb.type = 'checkbox'; cb.value = r.id; cb.checked = s.roi_selected.indexOf(r.id) >= 0;
        cb.addEventListener('change', function () { act('roi_select', { ids: selectedIds() }); });
        td.appendChild(cb);
        tr.appendChild(td);
        r.values.forEach(function (v, i) {
          var c = document.createElement('td');
          c.textContent = v;
          if (i === 0) { c.style.color = r.color; }
          tr.appendChild(c);
        });
        body.appendChild(tr);
      });
    }
    if (changed('roi-defaults', s.roi_defaults)) {
      ['roi', 'ph'].forEach(function (p) {
        $(p + '-nexp').value = String(s.roi_defaults.n_exp);
        $(p + '-tmin').value = s.roi_defaults.tau_min;
        $(p + '-tmax').value = s.roi_defaults.tau_max;
        $(p + '-cost').value = s.roi_defaults.cost_function;
      });
    }
    if (pendingFit && !s.running) {
      var key = JSON.stringify(pendingFit);
      if (s.roi_fits.some(function (k) { return JSON.stringify(k) === key; })) { viewFit(pendingFit, true); pendingFit = null; }
    }
  });

  $('btn-auto').addEventListener('click', function () { act('auto_scale'); });
  $('btn-update').addEventListener('click', function () {
    var f = {};
    document.querySelectorAll('#scale input[type=text][data-field]').forEach(function (el) { f[el.dataset.field] = el.value; });
    f['fov.cmap'] = document.querySelector('#scale select[data-field]').value;
    post('/api/set', f).then(function () { act('update_display'); });
  });
  $('z').addEventListener('change', function () { act('z', { i: parseInt($('z').value, 10) }); });
  $('roi-clear').addEventListener('click', function () { if (confirm('Clear all regions?')) { act('roi_clear'); } });
  $('roi-delete').addEventListener('click', function () {
    var ids = selectedIds();
    if (!ids.length) { toast('warning', 'Select a region first'); return; }
    act('roi_delete', { ids: ids });
  });
  $('roi-rename').addEventListener('click', function () {
    var ids = selectedIds();
    if (ids.length !== 1) { toast('warning', 'Select exactly one region to rename'); return; }
    act('roi_rename', { id: ids[0], name: $('roi-name').value }).then(function (out) { if (out.ok) { $('roi-name').value = ''; } });
  });
  $('roi-import').addEventListener('click', function () { act('roi_import', { path: $('roi-import-path').value }); });
  $('roi-export-csv').addEventListener('click', function () { act('roi_export_csv'); });
  $('roi-export-geojson').addEventListener('click', function () {
    var ids = selectedIds();
    if (!ids.length) { toast('warning', 'Select a region first'); return; }
    act('roi_export_geojson', { ids: ids });
  });
  $('roi-export-all').addEventListener('click', function () { act('roi_export_geojson', { ids: [] }); });
  $('roi-fit').addEventListener('click', function () {
    var ids = selectedIds().sort(function (a, b) { return a - b; });
    act('roi_fit', { ids: ids, n_exp: parseInt($('roi-nexp').value, 10), tau_min: $('roi-tmin').value,
                     tau_max: $('roi-tmax').value, cost_function: $('roi-cost').value })
      .then(function (out) { if (out.ok) { pendingFit = ids; } });
  });
  $('btn-clear-view').addEventListener('click', function () { act('clear_view'); });
  $('roi-view').addEventListener('click', function () {
    var ids = selectedIds().sort(function (a, b) { return a - b; });
    if (!ids.length) { toast('warning', 'Select a region in the list first.'); return; }
    viewFit(ids, false);
  });
})();
