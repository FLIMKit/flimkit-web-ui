from importlib.metadata import entry_points
from importlib.resources import files

import flimkit_web_ui
from flimkit import plugins


def test_api_version_matches():
    assert flimkit_web_ui.FLIMKIT_PLUGIN_API == plugins.API_VERSION


def test_startup_is_registered():
    assert 'web_ui' in [s.id for s in plugins.startups()]


def test_tool_is_registered():
    found = plugins.get_tool('open_web_ui')
    assert found is not None
    assert found.menu_path == ('Tools',)
    assert callable(found.callback)


def test_entry_point_is_declared():
    names = [e.name for e in entry_points(group='flimkit.plugins')]
    assert 'flimkit_web_ui' in names


def test_page_files_are_packaged():
    for nam in ('page.html', 'core.js', 'fov.js', 'modes.js'):
        assert files('flimkit_web_ui').joinpath(nam).is_file()
