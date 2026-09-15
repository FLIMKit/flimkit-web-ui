import io
import itertools
import os
import threading
import time

_windows = []
_figs = {}
_notes = []
_notes_lock = threading.Lock()
_note_ids = itertools.count(1)
_answers = {}
_flags = {'last_poll': 0.0, 'last_action': 0.0, 'rendering': False}

# The web UI owns dialogs only while a page is polling and was used recently,
# so a desktop-only session keeps its normal popups.
OWN_POLL_S = 6.0
OWN_ACTION_S = 1800.0


def mark_poll():
    _flags['last_poll'] = time.time()


def mark_action():
    _flags['last_action'] = time.time()


def web_owned():
    if os.environ.get('FLIMKIT_WEB_HEADLESS', '') not in ('', '0', 'false', 'False'):
        return True
    now = time.time()
    return now - _flags['last_poll'] < OWN_POLL_S and now - _flags['last_action'] < OWN_ACTION_S


def on_ui(app, fn, timeout=120.0):
    if threading.current_thread() is threading.main_thread():
        return fn()
    root = getattr(app, 'root', None)
    if root is None or callable(getattr(root, 'after', None)) == False:
        raise RuntimeError('FLIMKit UI is not available')
    done = threading.Event()
    outcome = {}

    def run():
        try:
            outcome['value'] = fn()
        except BaseException as exc:
            outcome['error'] = exc
        finally:
            done.set()

    root.after(0, run)
    if done.wait(timeout) == False:
        raise TimeoutError('The FLIMKit desktop window is busy - a dialog may be open there.')
    if 'error' in outcome:
        raise outcome['error']
    return outcome.get('value')


def add_note(level, title, message):
    with _notes_lock:
        _notes.append({'id': next(_note_ids), 'level': level, 'title': str(title or ''), 'message': str(message or '')})


def drain_notes():
    with _notes_lock:
        found = list(_notes)
        _notes.clear()
    return found


def answer(nam, value, later=False):
    _answers[nam] = {'value': value, 'later': later}


def _pop_answer(nam):
    entry = _answers.pop(nam, None)
    if entry is None:
        return False, None
    return True, entry['value']


def clear_answers():
    for nam in [k for k, v in _answers.items() if v['later'] == False]:
        _answers.pop(nam, None)


def _texts(a, kw):
    title = kw.get('title', a[0] if len(a) > 0 else '')
    message = kw.get('message', kw.get('prompt', a[1] if len(a) > 1 else ''))
    return title, message


def install_dialogs():
    from tkinter import filedialog, messagebox, simpledialog
    if getattr(messagebox, '_web_hooked', False) == True:
        return

    def wrap(mod, nam, level, default):
        orig = getattr(mod, nam)

        def inner(*a, **kw):
            title, message = _texts(a, kw)
            found, value = _pop_answer(nam)
            if found == True:
                if level != None:
                    add_note(level, title, message)
                return value
            if web_owned() == True:
                if level != None:
                    add_note(level, title, message)
                else:
                    add_note('warning', 'Desktop prompt skipped: ' + str(title), message)
                return default
            return orig(*a, **kw)

        setattr(mod, nam, inner)

    wrap(messagebox, 'showinfo', 'info', 'ok')
    wrap(messagebox, 'showwarning', 'warning', 'ok')
    wrap(messagebox, 'showerror', 'error', 'ok')
    wrap(messagebox, 'askyesno', None, False)
    wrap(messagebox, 'askokcancel', None, False)
    wrap(messagebox, 'askyesnocancel', None, None)
    wrap(simpledialog, 'askinteger', None, None)
    wrap(simpledialog, 'askfloat', None, None)
    wrap(simpledialog, 'askstring', None, None)
    wrap(filedialog, 'askopenfilename', None, '')
    wrap(filedialog, 'asksaveasfilename', None, '')
    wrap(filedialog, 'askdirectory', None, '')
    messagebox._web_hooked = True


def install_roi_hooks():
    import flimkit.UI.roi_tools as rt
    if getattr(rt, '_web_hooked', False) == True:
        return
    orig_window = rt._show_fit_result_window
    orig_options = rt._ask_roi_fit_options

    def show_window(result):
        if web_owned() == True:
            add_note('info', 'Fit complete', str(result.get('region_name', '')) + ' - press View Fit to see it.')
            return
        orig_window(result)

    def ask_options(params):
        found, opts = _pop_answer('roi_opts')
        if found == True:
            return dict(params, **opts)
        if web_owned() == True:
            add_note('warning', 'Fit options needed', 'Start the fit from the web UI.')
            return None
        return orig_options(params)

    rt._show_fit_result_window = show_window
    rt._ask_roi_fit_options = ask_options
    rt._web_hooked = True


def hook_progress():
    from flimkit.UI import progress_window as pw
    cls = pw.ProgressWindow
    if getattr(cls, '_web_hooked', False) == True:
        return
    orig_init = cls.__init__
    orig_close = cls.close

    def init(self, parent, task_name='Working...'):
        orig_init(self, parent, task_name=task_name)
        self._web_task = task_name
        _windows.append(self)

    def close(self):
        if self in _windows:
            _windows.remove(self)
        orig_close(self)

    cls.__init__ = init
    cls.close = close
    cls._web_hooked = True


def progress_state():
    found = []
    for win in list(_windows):
        try:
            found.append({
                'task': win._web_task,
                'value': float(win.progress['value']),
                'maximum': float(win.progress['maximum']),
                'status': win.status.get(),
            })
        except Exception:
            pass
    return found


def cancel_all():
    for win in list(_windows):
        try:
            win.cancel()
        except Exception:
            pass


def _fig_spec(app, key):
    if key == 'fov':
        p = app._fov_preview
        return p._fig, p._canvas_mpl, [('img', p._ax_img), ('flim', p._ax_flim)]
    if key == 'phasor':
        p = app._phasor_panel
        return p._fig, p._canvas, [('ph', p._ax_ph), ('img', p._ax_img)]
    if key == 'irf':
        if hasattr(app, '_irf_fig') == False:
            return None
        return app._irf_fig, app._irf_canvas_mpl, []
    return None


def _entry(key):
    if key not in _figs:
        _figs[key] = {'rev': 1, 'cache_rev': -1, 'png': b'', 'geom': {}, 'lock': threading.Lock()}
    return _figs[key]


def _hook_canvas(key, canvas):
    if getattr(canvas, '_web_hooked', False) == True:
        return
    ent = _entry(key)

    def wrap(fn):
        def inner(*a, **kw):
            if _flags['rendering'] == False:
                ent['rev'] += 1
            return fn(*a, **kw)
        return inner

    canvas.draw_idle = wrap(canvas.draw_idle)
    canvas.draw = wrap(canvas.draw)
    canvas._web_hooked = True


def fig_revs(app):
    found = {}
    for key in ('fov', 'phasor', 'irf'):
        spec = _fig_spec(app, key)
        if spec is None:
            continue
        _hook_canvas(key, spec[1])
        found[key] = _entry(key)['rev']
    return found


def render(app, key):
    ent = _entry(key)
    with ent['lock']:
        rev = ent['rev']
        if ent['cache_rev'] == rev:
            return ent['png'], ent['geom'], rev

        def draw():
            spec = _fig_spec(app, key)
            if spec is None:
                raise ValueError('No ' + key + ' figure yet.')
            fig, canvas, axes = spec
            _hook_canvas(key, canvas)
            buf = io.BytesIO()
            _flags['rendering'] = True
            try:
                fig.savefig(buf, format='png', dpi=fig.dpi, facecolor=fig.get_facecolor())
            finally:
                _flags['rendering'] = False
            geom = {}
            for nam, ax in axes:
                if ax.get_visible() == True:
                    pos = ax.get_position()
                    geom[nam] = {
                        'x0': pos.x0, 'y0': pos.y0, 'w': pos.width, 'h': pos.height,
                        'xlim': list(ax.get_xlim()), 'ylim': list(ax.get_ylim()),
                    }
            return buf.getvalue(), geom

        png, geom = on_ui(app, draw, timeout=30.0)
        ent['png'] = png
        ent['geom'] = geom
        ent['cache_rev'] = rev
        return png, geom, rev
