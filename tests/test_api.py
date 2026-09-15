import os
import types

import numpy as np
import pytest

pytest.importorskip('tkinter')

from flimkit_web_ui import api


class FakeVar:

    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_list_dir_puts_folders_first_and_hides_dotfiles(tmp_path):
    (tmp_path / 'b_folder').mkdir()
    (tmp_path / 'a_file.ptu').write_text('x')
    (tmp_path / '.hidden').write_text('x')
    listing = api.list_dir(str(tmp_path))
    assert listing['dir'] == str(tmp_path)
    assert listing['parent'] == str(tmp_path.parent)
    assert [(e['name'], e['is_dir']) for e in listing['entries']] == [('b_folder', True), ('a_file.ptu', False)]


def test_list_dir_falls_back_to_home_for_a_missing_folder(tmp_path):
    listing = api.list_dir(str(tmp_path / 'does_not_exist'))
    assert listing['dir'] == os.path.expanduser('~')


def test_fit_options_are_validated():
    opts = api._fit_opts({'n_exp': '2', 'tau_min': '0.1', 'tau_max': '20', 'cost_function': 'chi2'})
    assert opts == {'n_exp': 2, 'tau_min': 0.1, 'tau_max': 20.0, 'cost_function': 'chi2'}
    with pytest.raises(ValueError):
        api._fit_opts({'tau_min': 0})
    with pytest.raises(ValueError):
        api._fit_opts({'tau_min': 5, 'tau_max': 2})


def fit_result():
    time_ns = np.linspace(0, 12.5, 64)
    decay = 1000 * np.exp(-time_ns / 3.0) + 1
    return {
        'region_name': 'rect-1',
        'irf_source': 'from main fit',
        'decay': decay,
        'time_ns': time_ns,
        'irf_prompt': np.exp(-((time_ns - 1) ** 2) / 0.02),
        'summary': {'taus_ns': [2.0, 4.0], 'amps': [1.0, 3.0], 'reduced_chi2_tail': 1.1, 'model': decay * 0.98},
    }


def test_fit_rows_include_components_mean_and_chi2():
    rows = api.fit_rows(fit_result())
    assert rows['name'] == 'rect-1'
    table = {r[0]: r[1] for r in rows['rows']}
    assert table['τ1'] == '2.0000'
    assert table['τ2'] == '4.0000'
    assert table['τ_mean (amplitude-weighted)'] == '3.5000'
    assert table['χ²_r (tail)'] == '1.1000'


def test_fit_png_renders_a_png():
    assert api.fit_png(fit_result())[:8] == b'\x89PNG\r\n\x1a\n'


def test_set_fields_updates_state_vars_and_rejects_unknown_ones():
    app = types.SimpleNamespace(state=types.SimpleNamespace(sv_out_fov=FakeVar('old')))
    api.set_fields(app, {'sv_out_fov': 'new'})
    assert app.state.sv_out_fov.get() == 'new'
    with pytest.raises(ValueError):
        api.set_fields(app, {'sv_not_a_field': 1})


def test_unknown_actions_are_rejected():
    with pytest.raises(ValueError):
        api.run_action(types.SimpleNamespace(), 'not_an_action', {})


def test_about_runs_without_the_desktop():
    from flimkit._version import __version__
    out = api.run_action(types.SimpleNamespace(), 'about', {})
    assert __version__ in out['text']
    assert out['notes'] == []
