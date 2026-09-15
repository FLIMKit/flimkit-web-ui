import threading
import time

import pytest

from flimkit_web_ui import bridge

tkinter = pytest.importorskip('tkinter')


@pytest.fixture(autouse=True)
def clean():
    bridge._answers.clear()
    bridge.drain_notes()
    bridge._flags['last_poll'] = 0.0
    bridge._flags['last_action'] = 0.0
    yield
    bridge._answers.clear()
    bridge.drain_notes()


class InlineRoot:

    def after(self, delay, fn):
        fn()


class IgnoringRoot:

    def after(self, delay, fn):
        pass


def in_thread(fn):
    out = {}

    def run():
        try:
            out['value'] = fn()
        except BaseException as exc:
            out['error'] = exc

    t = threading.Thread(target=run)
    t.start()
    t.join()
    return out


def test_notes_drain_once():
    bridge.add_note('info', 'Title', 'message')
    notes = bridge.drain_notes()
    assert [(n['level'], n['title'], n['message']) for n in notes] == [('info', 'Title', 'message')]
    assert bridge.drain_notes() == []


def test_answers_are_one_shot_unless_kept_for_later():
    bridge.answer('now', 1)
    bridge.answer('later', 2, later=True)
    bridge.clear_answers()
    assert bridge._pop_answer('now') == (False, None)
    assert bridge._pop_answer('later') == (True, 2)
    assert bridge._pop_answer('later') == (False, None)


def test_web_owns_dialogs_only_while_polled_and_used():
    assert bridge.web_owned() == False
    bridge.mark_action()
    assert bridge.web_owned() == False
    bridge.mark_poll()
    assert bridge.web_owned() == True
    bridge._flags['last_poll'] = time.time() - bridge.OWN_POLL_S - 1
    assert bridge.web_owned() == False


def test_on_ui_runs_inline_on_the_main_thread():
    assert bridge.on_ui(object(), lambda: 5) == 5


def test_on_ui_schedules_through_root_after_from_a_worker():
    class App:
        root = InlineRoot()

    assert in_thread(lambda: bridge.on_ui(App(), lambda: 7)) == {'value': 7}


def test_on_ui_reraises_errors_from_the_ui_thread():
    class App:
        root = InlineRoot()

    def boom():
        raise ValueError('bad')

    out = in_thread(lambda: bridge.on_ui(App(), boom))
    assert isinstance(out['error'], ValueError)


def test_on_ui_times_out_when_the_ui_thread_is_blocked():
    class App:
        root = IgnoringRoot()

    out = in_thread(lambda: bridge.on_ui(App(), lambda: 1, timeout=0.1))
    assert isinstance(out['error'], TimeoutError)


def test_on_ui_without_a_root_fails_clearly():
    out = in_thread(lambda: bridge.on_ui(object(), lambda: 1))
    assert isinstance(out['error'], RuntimeError)


@pytest.fixture
def dialogs(monkeypatch):
    from tkinter import filedialog, messagebox, simpledialog
    calls = []

    def fake(nam, value):
        def inner(*a, **kw):
            calls.append(nam)
            return value
        return inner

    for mod, nam, value in [
        (messagebox, 'showinfo', 'ok'), (messagebox, 'showwarning', 'ok'), (messagebox, 'showerror', 'ok'),
        (messagebox, 'askyesno', True), (messagebox, 'askokcancel', True), (messagebox, 'askyesnocancel', True),
        (simpledialog, 'askinteger', 9), (simpledialog, 'askfloat', 9.0), (simpledialog, 'askstring', 'x'),
        (filedialog, 'askopenfilename', '/desktop'), (filedialog, 'asksaveasfilename', '/desktop'),
        (filedialog, 'askdirectory', '/desktop'),
    ]:
        monkeypatch.setattr(mod, nam, fake(nam, value))
    monkeypatch.setattr(messagebox, '_web_hooked', False, raising=False)
    bridge.install_dialogs()
    return calls


def test_desktop_dialogs_behave_normally_when_the_page_is_idle(dialogs):
    from tkinter import messagebox
    assert messagebox.showerror('Title', 'message') == 'ok'
    assert dialogs == ['showerror']
    assert bridge.drain_notes() == []


def test_dialogs_become_page_notices_while_the_page_is_in_use(dialogs):
    from tkinter import filedialog, messagebox
    bridge.mark_action()
    bridge.mark_poll()
    assert messagebox.showerror('Missing input', 'Pick a file') == 'ok'
    assert messagebox.askyesno('Overwrite?', 'Sure?') == False
    assert filedialog.askopenfilename(title='Open') == ''
    assert dialogs == []
    titles = [n['title'] for n in bridge.drain_notes()]
    assert titles == ['Missing input', 'Desktop prompt skipped: Overwrite?', 'Desktop prompt skipped: Open']


def test_queued_answers_are_used_instead_of_the_dialog(dialogs):
    from tkinter import simpledialog
    bridge.answer('askinteger', 3)
    assert simpledialog.askinteger('Select PTU Channel', 'Available channels: 1, 3') == 3
    assert dialogs == []
