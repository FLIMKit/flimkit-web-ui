import csv
import io
import os
import tempfile
from pathlib import Path

import numpy as np

from . import bridge

EXTRA_VARS = {
    'irf_fov.method': lambda app: app._irf_fov.sv_method,
    'irf_fov.path': lambda app: app._irf_fov.sv_path,
    'irf_st.method': lambda app: app._irf_st.sv_method,
    'irf_st.path': lambda app: app._irf_st.sv_path,
    'fov.tau_min': lambda app: app._fov_preview._sv_tau_min,
    'fov.tau_max': lambda app: app._fov_preview._sv_tau_max,
    'fov.gamma': lambda app: app._fov_preview._sv_gamma,
    'fov.cmap': lambda app: app._fov_preview._sv_cmap,
    'fov.show_decay': lambda app: app._fov_preview._bv_show_decay,
    'fov.view': lambda app: app._fov_preview._sv_display_mode,
    'fov.weighting': lambda app: app._fov_preview._sv_tau_weighting,
    'ph.mode': lambda app: app._phasor_panel._mode_var,
    'ph.radius': lambda app: app._phasor_panel._radius,
    'ph.ratio': lambda app: app._phasor_panel._ratio,
    'ph.filter_method': lambda app: app._phasor_panel._filter_method,
    'ph.filter_sigma': lambda app: app._phasor_panel._filter_sigma,
    'ph.filter_size': lambda app: app._phasor_panel._filter_size,
}


def _tog(app, var, entry):
    from flimkit.UI.utils import _tog as tog
    tog(getattr(app, var), getattr(app, entry))


def _tl_entries(app):
    state = 'normal' if app.bv_tl_fix_tau.get() == True else 'disabled'
    for e in (app._tl_tau1_e, app._tl_tau2_e, app._tl_tau3_e):
        e.config(state=state)


AFTER_SET = {
    'sv_fov_analysis': lambda app: app._on_fov_analysis_changed(),
    'bv_thr_fov': lambda app: _tog(app, 'bv_thr_fov', '_thr_fov_e'),
    'bv_thr_st': lambda app: _tog(app, 'bv_thr_st', '_thr_st_e'),
    'bv_batch_thr': lambda app: _tog(app, 'bv_batch_thr', '_batch_thr_e'),
    'bv_tl_fix_tau': _tl_entries,
    'sv_pipeline': lambda app: app._pipeline_changed(),
    'bv_perpix': lambda app: app._perpix_toggled(),
    'sv_batch_mode': lambda app: app._batch_mode_changed(),
    'sv_ph_mode': lambda app: app._ph_mode_changed(),
    'irf_fov.method': lambda app: app._irf_fov._update(),
    'irf_st.method': lambda app: app._irf_st._update(),
    'fov.show_decay': lambda app: app._fov_preview._toggle_decay(),
    'fov.view': lambda app: app._fov_preview._on_display_mode_changed(),
    'fov.weighting': lambda app: app._fov_preview._on_weighting_changed(),
    'ph.mode': lambda app: app._phasor_panel._on_mode_change(),
    'ph.radius': lambda app: app._phasor_panel._on_param_change(),
    'ph.ratio': lambda app: app._phasor_panel._on_param_change(),
}


def _var_table(app):
    table = {}
    for nam, var in app.state.__dict__.items():
        if callable(getattr(var, 'get', None)) and callable(getattr(var, 'set', None)):
            table[nam] = var
    for nam, get in EXTRA_VARS.items():
        try:
            table[nam] = get(app)
        except AttributeError:
            pass
    return table


def _coerce(var, value):
    import tkinter as tk
    if isinstance(var, tk.BooleanVar):
        return value == True or str(value).lower() == 'true'
    if isinstance(var, tk.IntVar):
        return int(float(value))
    if isinstance(var, tk.DoubleVar):
        return float(value)
    return '' if value is None else str(value)


def set_fields(app, values):
    bridge.mark_action()

    def do():
        table = _var_table(app)
        for key, value in values.items():
            if key not in table:
                raise ValueError('Unknown field ' + key)
            var = table[key]
            var.set(_coerce(var, value))
            if key in AFTER_SET:
                AFTER_SET[key](app)

    bridge.on_ui(app, do)
    return bridge.drain_notes()


def roi_panel(app):
    return app._fov_preview._roi_analysis_panel or app._roi_analysis_panel


def _btn_state(btn):
    return str(btn.cget('state')) == 'disabled'


def _btn_text(btn):
    return str(btn.cget('text')).lstrip('▶ ').strip()


def expert_values(app):
    from flimkit.UI.expert_settings import _EXPERT_DEFAULTS
    from flimkit.UI.utils import _C
    c = _C()
    vals = dict(_EXPERT_DEFAULTS)
    vals.update({
        'binning_factor': c['binning_factor'],
        'optimizer': c['Optimizer'],
        'lm_restarts': c['lm_restarts'],
        'de_population': c['de_population'],
        'de_maxiter': c['de_maxiter'],
        'n_workers': c['n_workers'],
        'min_photons': c['MIN_PHOTONS_PERPIX'],
    })
    try:
        from flimkit.utils.config_manager import cfg
        vals.update(cfg.get_section('expert') or {})
    except Exception:
        pass
    vals.update(app._expert_overrides or {})
    return vals


def _cursor_json(cur):
    if cur.get('type', 'ellipse') == 'poly':
        return {'type': 'poly', 'color': cur['color'], 'vertices': [[float(v[0]), float(v[1])] for v in cur['vertices']]}
    return {'type': 'ellipse', 'color': cur['color'], 'g': float(cur['center_g']), 's': float(cur['center_s'])}


def get_state(app):
    bridge.mark_poll()

    def read():
        from flimkit.UI.irf_widget import IRFWidget
        from flimkit.utils import display
        p = app._fov_preview
        res = app._res
        panel = roi_panel(app)
        ph = app._phasor_panel
        pb = app._proj_browser
        fields = {}
        for key, var in _var_table(app).items():
            try:
                fields[key] = var.get()
            except Exception:
                pass
        stack = p._series or p._zstack
        mgr = p._roi_manager
        rois = []
        for iid in panel._tree.get_children():
            rid = int(iid)
            rois.append({'id': rid, 'values': [str(v) for v in panel._tree.item(iid, 'values')], 'color': mgr.get_color(rid)})
        fit = res._fit_result or {}
        try:
            roi_defaults = app._get_roi_fit_params()
            roi_defaults = {k: roi_defaults.get(k) for k in ('n_exp', 'tau_min', 'tau_max', 'cost_function')}
        except Exception:
            roi_defaults = {'n_exp': 1, 'tau_min': 0.1, 'tau_max': 25.0, 'cost_function': 'poisson'}
        log = res.log.get('1.0', 'end')
        buttons = {'fov': app._btn_fov, 'stitch': app._btn_st, 'phasor': app._btn_ph,
                   'batch': app._btn_batch, 'irf': app._btn_mirf}
        progress = bridge.progress_state()
        return {
            'form': getattr(app, '_current_form', 'fov'),
            'fields': fields,
            'choices': {'irf': [list(c) for c in IRFWidget.CHOICES], 'cmap': list(display.COLORMAPS.keys())},
            'run_labels': {k: _btn_text(b) for k, b in buttons.items()},
            'busy': {k: _btn_state(b) for k, b in buttons.items()},
            'running': any(_btn_state(b) for b in (app._btn_fov, app._btn_st, app._btn_ph)) or len(progress) > 0,
            'progress': progress,
            'preview_status': p._status.get(),
            'results_status': res._status.get(),
            'scale_controls': bool(p._ctrl_frame.grid_info()),
            'z': {'i': p._z_i, 'n': len(stack), 'label': p._z_label.get()} if stack else None,
            'summary': [[str(v) for v in res._tv.item(i, 'values')] for i in res._tv.get_children()],
            'log_tail': log[-20000:],
            'log_len': len(log),
            'images': [str(x) for x in res._imgs],
            'export_images': sorted(k for k, v in fit.items()
                                    if isinstance(v, np.ndarray) and (v.ndim == 2 or (v.ndim == 3 and v.shape[2] == 3))),
            'output_dir': str(res._output_dir or ''),
            'npz_path': str(res._current_npz_path or ''),
            'rois': rois,
            'roi_selected': [int(i) for i in panel._tree.selection()],
            'roi_mode': panel._current_mode.get(),
            'roi_status': panel._status.get(),
            'roi_fits': [list(k) for k in panel._last_fit_results.keys()],
            'roi_can_fit': callable(getattr(panel, 'get_fit_params', None)),
            'roi_defaults': roi_defaults,
            'expert': expert_values(app),
            'expert_active': bool(app._expert_overrides),
            'phasor': {
                'loaded': ph._real is not None,
                'status': ph._status_var.get(),
                'freq': float(ph._freq or 0.0),
                'cursors': [_cursor_json(c) for c in ph._cursors],
                'max_cursors': ph.max_cursors,
                'has_fit': ph._last_fit_result is not None,
                'peaks': [] if ph._peak_results is None else [
                    {'g': float(ph._peak_results['peak_g'][i]), 's': float(ph._peak_results['peak_s'][i]),
                     'tau': float(ph._peak_results['tau_phase'][i])}
                    for i in range(int(ph._peak_results['n_peaks']))],
            },
            'batch': {
                'label': str(app._batch_mode_label.cget('text')),
                'help': str(app._batch_io_help.cget('text')),
                'beside': app.sv_batch_save_beside_preview.get(),
            },
            'project': {
                'status': pb._sv_status.get(),
                'items': [str(x) for x in pb._lb.get(0, 'end')],
                'selected': [int(i) for i in pb._lb.curselection()],
            },
            'recent': [dict(e) for e in app._recent_files],
            'figs': bridge.fig_revs(app),
        }

    state = bridge.on_ui(app, read, timeout=8.0)
    state['notes'] = bridge.drain_notes()
    return state


def list_dir(directory):
    directory = os.path.abspath(os.path.expanduser(directory or '~'))
    if os.path.isdir(directory) == False:
        directory = os.path.expanduser('~')
    entries = []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.name.startswith('.'):
                    continue
                try:
                    is_dir = entry.is_dir()
                except OSError:
                    continue
                entries.append({'name': entry.name, 'path': entry.path, 'is_dir': is_dir})
    except OSError as exc:
        return {'error': str(exc)}
    entries.sort(key=lambda e: (e['is_dir'] == False, e['name'].lower()))
    parent = os.path.dirname(directory)
    return {'dir': directory, 'parent': parent if parent != directory else None, 'entries': entries}


def _stem(app):
    ptu = app._fov_preview._ptu_path
    return Path(str(ptu)).stem if ptu else 'flimkit'


def _select(app, ids):
    panel = roi_panel(app)
    p = app._fov_preview
    current = panel._tree.selection()
    if current:
        panel._tree.selection_remove(current)
    if ids:
        panel._tree.selection_set([str(i) for i in ids])
    p._roi_manager.select_region(ids[0] if ids else None)
    p._redraw_region_overlays()


def _capture(call, nam, mime):
    fd, tmp = tempfile.mkstemp(suffix=Path(nam).suffix)
    os.close(fd)
    os.remove(tmp)
    bridge.answer('asksaveasfilename', tmp)
    call()
    if os.path.exists(tmp) == False:
        return {}
    with open(tmp, encoding='utf-8') as f:
        text = f.read()
    os.remove(tmp)
    return {'download': {'name': nam, 'mime': mime, 'text': text}}


def _ids(args):
    return [int(i) for i in args.get('ids', [])]


def _need_idle(app):
    if any(_btn_state(b) for b in (app._btn_fov, app._btn_st, app._btn_ph)) or bridge.progress_state():
        raise ValueError('A task is already running.')


def fit_rows(result):
    summary = result['summary']
    taus = list(summary.get('taus_ns', []))
    amps = list(summary.get('amps', []))
    chi2 = summary.get('reduced_chi2_tail')
    rows = [['τ' + str(i + 1), '%.4f' % t, 'ns'] for i, t in enumerate(taus)]
    rows += [['A' + str(i + 1) + ' (amplitude)', '%.4f' % a, ''] for i, a in enumerate(amps)]
    if taus and amps and np.sum(amps) > 0:
        rows.append(['τ_mean (amplitude-weighted)', '%.4f' % float(np.dot(taus, amps) / np.sum(amps)), 'ns'])
    if chi2 is not None:
        rows.append(['χ²_r (tail)', '%.4f' % chi2, ''])
    return {'name': result['region_name'], 'irf_source': result['irf_source'], 'rows': rows}


def fit_png(result):
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure
    decay = np.asarray(result['decay'])
    time_ns = np.asarray(result['time_ns'])
    irf = result['irf_prompt']
    model = result['summary'].get('model')
    fig = Figure(figsize=(6.2, 4.2), facecolor='#2b2b2b')
    FigureCanvasAgg(fig)
    ax_d = fig.add_subplot(4, 1, (1, 3))
    ax_r = fig.add_subplot(4, 1, 4, sharex=ax_d)
    for ax in (ax_d, ax_r):
        ax.set_facecolor('#1e1e1e')
        ax.tick_params(colors='white', labelsize=8)
    ax_d.semilogy(time_ns, decay, 'o-', color='steelblue', linewidth=1.2, markersize=2, label='Decay', alpha=0.8)
    if irf is not None and np.max(irf) > 0:
        irf = np.asarray(irf)
        irf_sc = (irf / np.max(irf)) * decay.max() * 0.15
        ax_d.semilogy(time_ns[:len(irf)], np.maximum(irf_sc, 1e-2), color='orange', linewidth=1.5,
                      label='IRF (' + str(result['irf_source']) + ')', alpha=0.7)
    if model is not None and len(model) == len(decay):
        model = np.asarray(model)
        ax_d.semilogy(time_ns, model, color='red', linewidth=2.0, label='Fit', alpha=0.9)
        with np.errstate(invalid='ignore', divide='ignore'):
            resid = np.where(model > 0, (decay - model) / np.sqrt(model), 0.0)
        ax_r.plot(time_ns, resid, color='steelblue', linewidth=0.9)
        ax_r.axhline(0, color='red', linewidth=1.0, linestyle='--', alpha=0.7)
    ax_d.legend(fontsize=7, loc='upper right', labelcolor='white', facecolor='#333333', edgecolor='#555555')
    ax_d.set_title(str(result['region_name']), fontsize=9, color='white')
    ax_r.set_xlabel('Time (ns)', color='white', fontsize=8)
    fig.tight_layout(pad=0.8)
    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor=fig.get_facecolor())
    return buf.getvalue()


def fit_result(app, src, ids):
    def get():
        if src == 'phasor':
            return app._phasor_panel._last_fit_result
        return roi_panel(app)._last_fit_results.get(tuple(sorted(ids)))
    result = bridge.on_ui(app, get)
    if result is None:
        raise ValueError('No fit result cached for this selection yet.')
    return result


def result_image(app, i):
    path = bridge.on_ui(app, lambda: Path(app._res._imgs[i]))
    if path.suffix.lower() == '.png':
        return path.read_bytes()
    from PIL import Image
    buf = io.BytesIO()
    Image.open(path).convert('RGB').save(buf, format='PNG')
    return buf.getvalue()


# ---------- Single FOV, display, results ----------

def act_run_fov(app, args):
    _need_idle(app)
    if app.sv_fov_analysis.get() == 'zstack':
        if Path(app.sv_zstack_dir.get().strip() or '.missing').is_dir() == False:
            raise ValueError('Please select a valid z-stack folder.')
    else:
        ptu = app.sv_ptu.get().strip()
        if ptu == '' or Path(ptu).exists() == False:
            raise ValueError('Please select a valid PTU file.')
    app._run_fov()


def act_cancel(app, args):
    bridge.cancel_all()


def act_switch_form(app, args):
    form = str(args.get('form', 'fov'))
    if form not in ('fov', 'stitch', 'phasor', 'batch', 'irf'):
        raise ValueError('Unknown mode ' + form)
    app._switch_form(form)


def act_auto_scale(app, args):
    app._fov_preview._auto_detect_scale()


def act_update_display(app, args):
    app._fov_preview._update_flim_display()


def act_z(app, args):
    app._fov_preview._on_z_slider(int(args.get('i', 0)))


def act_clear_log(app, args):
    app._res._clear_log()


def act_save_log(app, args):
    text = app._res.log.get('1.0', 'end')
    return {'download': {'name': _stem(app) + '_log.txt', 'mime': 'text/plain', 'text': text}}


def act_export_summary_csv(app, args):
    tv = app._res._tv
    rows = [tv.item(i, 'values') for i in tv.get_children()]
    if not rows:
        raise ValueError('No summary data to export.')
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(['Parameter', 'Value', 'Unit'])
    writer.writerows(rows)
    return {'download': {'name': _stem(app) + '_summed_fit.csv', 'mime': 'text/csv', 'text': buf.getvalue()}}


def act_export_images(app, args):
    fit = app._res._fit_result or {}
    selected = {k: fit[k] for k in args.get('images', []) if k in fit}
    if not selected:
        raise ValueError('Please select at least one image to export.')
    path = str(args.get('path', '') or '').strip() or str(app._res._output_dir or '')
    if path == '':
        raise ValueError('Please select an export directory.')
    app._export_images(selected, path,
                       with_scalebar=args.get('scalebar', True) == True,
                       with_annotations=args.get('annotations', True) == True,
                       format=args.get('format', 'png'),
                       fit_result=fit)
    return {'message': 'Results exported to ' + path}


def act_save_session(app, args):
    folder = str(args.get('path', '')).strip()
    if folder == '':
        raise ValueError('Choose a folder to save the session into.')
    bridge.answer('askdirectory', folder)
    bridge.answer('askyesno', True)
    app._save_npz_quick(str(app._res._output_dir or ''))


def act_save_npz_as(app, args):
    path = str(args.get('path', '')).strip()
    if path == '':
        raise ValueError('Enter the .npz file path to save to.')
    bridge.answer('asksaveasfilename', path)
    app._menu_save_npz_as()


def act_load_session(app, args):
    path = str(args.get('path', '')).strip()
    if path == '' or Path(path).is_file() == False:
        raise ValueError('Choose a .npz session file.')
    app._load_fitted_data_from_file(path)


def act_menu_reset(app, args):
    bridge.answer('askyesno', True)
    app._menu_reset()


# ---------- ROIs ----------

def act_roi_mode(app, args):
    roi_panel(app)._set_mode(str(args.get('mode', 'select')))


def act_roi_add(app, args):
    tool = str(args.get('tool', ''))
    if tool not in ('rect', 'ellipse', 'polygon', 'freehand'):
        raise ValueError('Unknown ROI tool ' + tool)
    p = app._fov_preview
    p._draw_coords = [[float(x), float(y)] for x, y in args.get('coords', [])]
    p._finalize_drawing(tool)


def act_roi_select(app, args):
    _select(app, _ids(args))


def act_roi_delete(app, args):
    p = app._fov_preview
    for rid in _ids(args):
        p._roi_manager.remove_region(rid)
    p._redraw_region_overlays()
    p._save_regions_update()
    roi_panel(app)._refresh_region_list()


def act_roi_rename(app, args):
    name = str(args.get('name', '')).strip()
    if name == '':
        raise ValueError('Enter a name.')
    p = app._fov_preview
    p._roi_manager.update_region(int(args['id']), name=name)
    p._save_regions_update()
    roi_panel(app)._refresh_region_list()


def act_roi_clear(app, args):
    roi_panel(app)._clear_all_regions()


def act_roi_import(app, args):
    path = str(args.get('path', '')).strip()
    if path == '':
        raise ValueError('Choose a GeoJSON file.')
    bridge.answer('askopenfilename', path)
    roi_panel(app)._import_rois_geojson()


def act_roi_export_csv(app, args):
    return _capture(roi_panel(app)._export_all_rois_csv, _stem(app) + '_roi_data.csv', 'text/csv')


def act_roi_export_geojson(app, args):
    panel = roi_panel(app)
    ids = _ids(args)
    if ids:
        _select(app, ids[:1])
        return _capture(panel._export_selected_region, _stem(app) + '_roi_' + str(ids[0]) + '.geojson', 'application/geo+json')
    return _capture(panel._export_all_rois_geojson, _stem(app) + '_all_rois.geojson', 'application/geo+json')


def _fit_opts(args):
    opts = {
        'n_exp': int(args.get('n_exp', 1)),
        'tau_min': float(args.get('tau_min', 0.1)),
        'tau_max': float(args.get('tau_max', 25.0)),
        'cost_function': str(args.get('cost_function', 'poisson')),
    }
    if opts['tau_min'] <= 0 or opts['tau_max'] <= opts['tau_min']:
        raise ValueError('Need 0 < τ_min < τ_max.')
    return opts


def act_roi_fit(app, args):
    ids = _ids(args)
    if not ids:
        raise ValueError('Select a region in the list first.')
    bridge.answer('roi_opts', _fit_opts(args))
    _select(app, ids)
    roi_panel(app)._fit_roi_decay()


def act_fit_rows(app, args):
    getter = app._phasor_panel._last_fit_result if args.get('src') == 'phasor' \
        else roi_panel(app)._last_fit_results.get(tuple(sorted(_ids(args))))
    if getter is None:
        raise ValueError('No fit result cached for this selection yet.')
    return fit_rows(getter)


# ---------- expert settings ----------

def _expert_parse(raw):
    from flimkit.interactive import parse_exclude_ns

    def num(key, default, cast):
        s = str(raw.get(key) if raw.get(key) is not None else '').strip()
        return cast(s) if s != '' else default

    ch = str(raw.get('channels', '') or '').strip()
    excl = str(raw.get('exclude_ns', '') or '').strip()
    parse_exclude_ns(excl or None)
    return {
        'optimizer': str(raw.get('optimizer', 'de')),
        'de_population': num('de_population', 30, int),
        'de_maxiter': num('de_maxiter', 5000, int),
        'lm_restarts': num('lm_restarts', 8, int),
        'binning_factor': num('binning_factor', 1, int),
        'n_workers': num('n_workers', -1, int),
        'min_photons': num('min_photons', 10, int),
        'cost_function': str(raw.get('cost_function', 'poisson')),
        'channels': int(ch) if ch.isdigit() else (None if ch == '' else ch),
        'irf_fwhm': num('irf_fwhm', None, float),
        'irf_align': str(raw.get('irf_align', 'steepest_rise')),
        'irf_shift_bins': num('irf_shift_bins', 2, int),
        'align_irf': raw.get('align_irf') == True,
        'free_tau_perpixel': raw.get('free_tau_perpixel') == True,
        'pileup_in_model': raw.get('pileup_in_model') == True,
        'bg_in_model': raw.get('bg_in_model') == True,
        'fit_t0': raw.get('fit_t0') == True,
        'fit_start_ns': num('fit_start_ns', None, float),
        'fit_end_ns': num('fit_end_ns', None, float),
        'exclude_ns': excl,
    }


def _expert_apply(app, result):
    from flimkit.UI.expert_settings import _EXPERT_DEFAULTS
    from flimkit.utils.config_manager import cfg
    is_default = all(result.get(k) == v for k, v in _EXPERT_DEFAULTS.items())
    app._expert_overrides = {} if is_default == True else result
    cfg.update_section('expert', result)
    browser = getattr(app, '_proj_browser', None)
    if browser and browser._project:
        browser._project.config['expert'] = result
        browser._project.save()
        cfg.load_project_overrides(browser._project.config)
    app._update_expert_banners()


def act_expert_save(app, args):
    _expert_apply(app, _expert_parse(args.get('values', {})))


def act_expert_reset(app, args):
    from flimkit.UI.expert_settings import _EXPERT_DEFAULTS
    _expert_apply(app, dict(_EXPERT_DEFAULTS))


ACTIONS = {
    'run_fov': act_run_fov,
    'cancel': act_cancel,
    'switch_form': act_switch_form,
    'auto_scale': act_auto_scale,
    'update_display': act_update_display,
    'z': act_z,
    'clear_log': act_clear_log,
    'save_log': act_save_log,
    'export_summary_csv': act_export_summary_csv,
    'export_images': act_export_images,
    'save_session': act_save_session,
    'save_npz_as': act_save_npz_as,
    'load_session': act_load_session,
    'menu_reset': act_menu_reset,
    'roi_mode': act_roi_mode,
    'roi_add': act_roi_add,
    'roi_select': act_roi_select,
    'roi_delete': act_roi_delete,
    'roi_rename': act_roi_rename,
    'roi_clear': act_roi_clear,
    'roi_import': act_roi_import,
    'roi_export_csv': act_roi_export_csv,
    'roi_export_geojson': act_roi_export_geojson,
    'roi_fit': act_roi_fit,
    'fit_rows': act_fit_rows,
    'expert_save': act_expert_save,
    'expert_reset': act_expert_reset,
}


def run_action(app, name, args):
    from . import api_modes
    bridge.mark_action()
    off_ui = api_modes.OFF_UI.get(name)
    fn = off_ui or ACTIONS.get(name) or api_modes.ACTIONS.get(name)
    if fn is None:
        raise ValueError('Unknown action ' + str(name))

    def do():
        try:
            return fn(app, args) or {}
        finally:
            bridge.clear_answers()

    try:
        out = do() if off_ui is not None else bridge.on_ui(app, do)
    except Exception:
        bridge.clear_answers()
        raise
    out['notes'] = bridge.drain_notes()
    return out
