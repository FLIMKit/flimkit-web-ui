import os
import types
from pathlib import Path

from . import bridge
from .api import _btn_state, _fit_opts, _need_idle


# ---------- Tile Stitch, Batch, Machine IRF ----------

def act_run_stitch(app, args):
    _need_idle(app)
    app._run_stitch()


def act_batch_mode(app, args):
    mode = str(args.get('mode', 'tiled'))
    if mode not in ('tiled', 'fov', 'timelapse'):
        raise ValueError('Unknown batch mode ' + mode)
    app._menu_batch_processing(mode)


def act_run_batch(app, args):
    _need_idle(app)
    app._dispatch_batch()


def act_run_irf(app, args):
    _need_idle(app)
    app._run_build_machine_irf()


# ---------- Phasor ----------

def _ph_loaded(app):
    p = app._phasor_panel
    if p._real is None:
        raise ValueError('Load a PTU file first.')
    return p


def act_run_phasor(app, args):
    if _btn_state(app._btn_ph) == True:
        raise ValueError('Phasor analysis is already running.')
    bridge._answers.pop('askfloat', None)
    ch = str(args.get('channel', '') or '').strip()
    if ch != '':
        bridge.answer('askinteger', int(ch))
    freq = str(args.get('frequency', '') or '').strip()
    if freq != '':
        bridge.answer('askfloat', float(freq), later=True)
    app._run_phasor()


def act_ph_add_ellipse(app, args):
    p = _ph_loaded(app)
    p._on_click_ellipse(types.SimpleNamespace(xdata=float(args['g']), ydata=float(args['s'])))


def act_ph_add_poly(app, args):
    p = _ph_loaded(app)
    verts = [(float(x), float(y)) for x, y in args.get('vertices', [])]
    if len(verts) < 3:
        raise ValueError('A polygon needs at least 3 vertices.')
    if len(p._cursors) >= p.max_cursors:
        raise ValueError('Max ' + str(p.max_cursors) + ' cursors - clear or undo first.')
    p._poly_pts = verts
    p._commit_polygon()


def act_ph_move(app, args):
    p = _ph_loaded(app)
    i = int(args['i'])
    cur = p._cursors[i]
    if cur.get('type', 'ellipse') == 'poly':
        vs = cur['vertices']
        anchor = (sum(v[0] for v in vs) / len(vs), sum(v[1] for v in vs) / len(vs))
    else:
        anchor = (cur['center_g'], cur['center_s'])
    p._drag_idx = i
    p._drag_last = anchor
    p._do_drag(float(args['g']), float(args['s']))
    p._on_release(types.SimpleNamespace(inaxes=None, xdata=None, ydata=None))


def act_ph_clear(app, args):
    app._phasor_panel._on_clear()


def act_ph_undo(app, args):
    app._phasor_panel._on_undo()


def act_ph_filter_apply(app, args):
    _ph_loaded(app)._on_filter_apply()


def act_ph_filter_reset(app, args):
    _ph_loaded(app)._on_filter_reset()


def act_ph_find_peaks(app, args):
    app._run_ph_find_peaks()


def act_ph_fret_overlay(app, args):
    app._run_ph_fret_overlay()


def act_ph_fit_fret(app, args):
    app._run_ph_fit_fret()


def act_ph_clear_overlay(app, args):
    app._phasor_panel.clear_fret_overlay()


def act_ph_fit_decay(app, args):
    p = _ph_loaded(app)
    bridge.answer('roi_opts', _fit_opts(args))
    p._fit_cursor_decay()


def act_ph_save_session(app, args):
    path = str(args.get('path', '')).strip()
    if path == '':
        raise ValueError('Enter the .npz path to save the phasor session to.')
    bridge.answer('asksaveasfilename', path)
    _ph_loaded(app)._on_save()


# ---------- project browser, recent files ----------

def act_open_project(app, args):
    path = str(args.get('path', '')).strip()
    if path == '' or Path(path).is_dir() == False:
        raise ValueError('Choose a project folder.')
    app._proj_browser.load_folder(path)
    app._add_to_recent(path, 'project')


def act_project_select(app, args):
    pb = app._proj_browser
    lb = pb._lb
    lb.selection_clear(0, 'end')
    lb.selection_set(int(args['i']))
    pb._on_select()


def act_recent_open(app, args):
    app._load_recent_item(app._recent_files[int(args['i'])])


def act_recent_clear(app, args):
    app._clear_recent_files()


# ---------- tools that do not touch Tk ----------

def _floats(s):
    return [float(x) for x in str(s).split(',') if x.strip()]


def act_synth_generate(app, args):
    from flimkit import synth
    v = args.get('values', {})
    out_dir = str(args.get('out_dir', '')).strip()
    if out_dir == '':
        raise ValueError('Choose an output folder for the PTUs.')
    taus = _floats(v.get('tau', '4.1'))
    if not taus:
        raise ValueError('Enter at least one lifetime.')
    res_ns = float(v.get('res', 25)) / 1000.0
    refl = None
    if str(v.get('refl_ns', '')).strip() != '':
        refl = dict(center_ns=float(v['refl_ns']), frac=float(v.get('refl_frac', 0.02)), width_ns=0.15)
    pileup = float(v['pileup']) if str(v.get('pileup', '')).strip() != '' else None
    side = int(v.get('image', 16))
    sdt = args.get('sdt') == True
    common = dict(tau_ns=taus[0] if len(taus) == 1 else taus,
                  amps=_floats(v.get('amps', '')) or None,
                  n_bins=int(round(float(v.get('period', 50)) / res_ns)),
                  tcspc_res_ns=res_ns,
                  irf_fwhm_ns=float(v.get('irf_fwhm', 0.15)),
                  irf_center_ns=float(v.get('irf_center', 2.0)),
                  pileup_pp=pileup)
    photons = _floats(v.get('photons', '1e5'))
    name = str(v.get('name', 'synth')) or 'synth'
    if len(photons) == 1:
        synth.generate(out_dir, name=name, ny=side, nx=side, n_photons=photons[0],
                       reflection=refl, sdt=sdt, **common)
    else:
        synth.generate_series(out_dir, photons, name=name, with_reflection=refl is not None,
                              reflection=refl, ny=side, nx=side, sdt=sdt, **common)
    fmt = 'PTU + SDT' if sdt == True else 'PTU'
    return {'message': 'Wrote ' + str(len(photons)) + ' sample(s) (' + fmt + ') + IRF + truth JSON to ' + out_dir}


def act_prefs_get(app, args):
    from flimkit import plugins
    from flimkit.utils.config_manager import cfg
    p = cfg.get_section('preferences') or {}
    return {'prefs': {
        'colormap': p.get('colormap', 'viridis'),
        'font_size': p.get('font_size', 9),
        'default_nexp': p.get('default_nexp', 2),
        'export_format': p.get('export_format', 'CSV'),
        'output_directory': p.get('output_directory', '') or os.path.expanduser('~/FLIMKit/output'),
        'auto_save_npz': p.get('auto_save_npz', True),
        'plugins_enabled': plugins.plugins_enabled(),
        'user_plugins': plugins.user_plugins_allowed(),
        'plugin_dirs': '\n'.join(plugins.config_dirs()),
        'user_dir': plugins.user_dir(),
    }}


def act_prefs_save(app, args):
    from flimkit import plugins
    from flimkit.utils.config_manager import cfg
    v = args.get('values', {})
    plugins.set_plugins_enabled(v.get('plugins_enabled') == True)
    plugins.allow_user_plugins(v.get('user_plugins') == True)
    plugins.set_config_dirs([line.strip() for line in str(v.get('plugin_dirs', '')).splitlines()])
    cfg.update_section('preferences', {
        'colormap': str(v.get('colormap', 'viridis')),
        'font_size': int(v.get('font_size', 9)),
        'default_nexp': int(v.get('default_nexp', 2)),
        'export_format': str(v.get('export_format', 'CSV')),
        'output_directory': str(v.get('output_directory', '')),
        'auto_save_npz': v.get('auto_save_npz') == True,
    })
    return {'message': 'Preferences saved. Plugin changes take effect on the next start.'}


def act_plugins_info(app, args):
    from flimkit import plugins
    off = plugins.disabled_plugins()
    names = sorted({plugins.short_name(r.source) for r in plugins.load_report()} | set(off))
    return {
        'report': app._plugin_report_text(),
        'plugins': [{'name': n, 'enabled': n not in off} for n in names],
        'user_plugins': plugins.user_plugins_allowed(),
    }


def act_plugin_toggle(app, args):
    from flimkit import plugins
    plugins.set_plugin_disabled(str(args['name']), args.get('enabled') != True)
    return {'message': 'Saved. Takes effect on the next start.'}


def act_enable_user_plugins(app, args):
    from flimkit import plugins
    plugins.allow_user_plugins(True)
    return {'message': 'User plugins load on the next start of FLIMKit.'}


def act_about(app, args):
    from flimkit._version import __version__
    return {'text': 'FLIMKit Analysis GUI\n\nVersion: ' + str(__version__) + '\n\n'
                    'Single FOV and tile stitching, ROI lifetime analysis, machine IRF calibration, '
                    'batch processing, GeoJSON and CSV export.\n\n'
                    'Designed, developed, and maintained by Alex Hunt.'}


def act_update_check(app, args):
    from flimkit.utils.update_check import check_installation_freshness, format_update_report
    return {'text': format_update_report(check_installation_freshness(timeout=3.0, do_fetch=True))}


def _log_files():
    import glob
    from flimkit.utils.crash_handler import get_log_dir
    log_dir = get_log_dir()
    return glob.glob(os.path.join(log_dir, '*.log')) if os.path.exists(log_dir) else []


def act_error_logs(app, args):
    from flimkit.utils.crash_handler import build_export_report
    if not _log_files():
        return {'text': 'No error logs found.'}
    return {'text': build_export_report(include_all_sessions=False)}


def act_export_error_logs(app, args):
    from flimkit.utils.crash_handler import build_export_report
    if not _log_files():
        raise ValueError('No error logs found to export.')
    return {'download': {'name': 'flimkit_error_report.log', 'mime': 'text/plain',
                         'text': build_export_report(include_all_sessions=True)}}


ACTIONS = {
    'run_stitch': act_run_stitch,
    'batch_mode': act_batch_mode,
    'run_batch': act_run_batch,
    'run_irf': act_run_irf,
    'run_phasor': act_run_phasor,
    'ph_add_ellipse': act_ph_add_ellipse,
    'ph_add_poly': act_ph_add_poly,
    'ph_move': act_ph_move,
    'ph_clear': act_ph_clear,
    'ph_undo': act_ph_undo,
    'ph_filter_apply': act_ph_filter_apply,
    'ph_filter_reset': act_ph_filter_reset,
    'ph_find_peaks': act_ph_find_peaks,
    'ph_fret_overlay': act_ph_fret_overlay,
    'ph_fit_fret': act_ph_fit_fret,
    'ph_clear_overlay': act_ph_clear_overlay,
    'ph_fit_decay': act_ph_fit_decay,
    'ph_save_session': act_ph_save_session,
    'open_project': act_open_project,
    'project_select': act_project_select,
    'recent_open': act_recent_open,
    'recent_clear': act_recent_clear,
}

OFF_UI = {
    'synth_generate': act_synth_generate,
    'prefs_get': act_prefs_get,
    'prefs_save': act_prefs_save,
    'plugins_info': act_plugins_info,
    'plugin_toggle': act_plugin_toggle,
    'enable_user_plugins': act_enable_user_plugins,
    'about': act_about,
    'update_check': act_update_check,
    'error_logs': act_error_logs,
    'export_error_logs': act_export_error_logs,
}
