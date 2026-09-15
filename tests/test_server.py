import json
import threading
import types
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

pytest.importorskip('tkinter')

from flimkit_web_ui import server


class InlineRoot:

    def after(self, delay, fn):
        fn()


@pytest.fixture
def base():
    app = types.SimpleNamespace(root=InlineRoot(), _phasor_panel=types.SimpleNamespace(_last_fit_result=None))
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), server.make_handler(app))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield 'http://127.0.0.1:' + str(httpd.server_address[1])
    httpd.shutdown()
    httpd.server_close()


def request(url, body=None):
    data = None if body is None else json.dumps(body).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers, exc.read()


def test_page_is_served_without_caching(base):
    status, headers, body = request(base + '/')
    assert status == 200
    assert b'FLIMKit Web UI' in body
    assert headers['Cache-Control'] == 'no-store'


@pytest.mark.parametrize('nam', ['core.js', 'fov.js', 'modes.js'])
def test_scripts_are_served(base, nam):
    status, headers, body = request(base + '/' + nam)
    assert status == 200
    assert 'javascript' in headers['Content-Type']
    assert len(body) > 0


def test_unknown_paths_404(base):
    assert request(base + '/nope')[0] == 404


def test_browse_lists_a_folder(base, tmp_path):
    (tmp_path / 'sample.ptu').write_text('x')
    status, headers, body = request(base + '/api/browse?dir=' + urllib.request.quote(str(tmp_path)))
    listing = json.loads(body)
    assert status == 200
    assert [e['name'] for e in listing['entries']] == ['sample.ptu']


def test_missing_fit_plot_is_a_404_with_a_message(base):
    status, headers, body = request(base + '/api/fit.png?src=phasor')
    assert status == 404
    assert 'No fit result' in json.loads(body)['error']


def test_unknown_action_is_a_400(base):
    status, headers, body = request(base + '/api/action', {'name': 'not_an_action'})
    assert status == 400
    assert json.loads(body)['ok'] == False


def test_off_ui_action_returns_its_result(base):
    status, headers, body = request(base + '/api/action', {'name': 'about'})
    out = json.loads(body)
    assert status == 200
    assert out['ok'] == True
    assert 'FLIMKit' in out['text']


def login(user, password):
    import base64
    return 'Basic ' + base64.b64encode((user + ':' + password).encode('utf-8')).decode('ascii')


def authed(url, header):
    req = urllib.request.Request(url, headers={'Authorization': header} if header else {})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.headers
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers


def test_everything_is_open_without_a_password(base, monkeypatch):
    monkeypatch.delenv('FLIMKIT_WEB_PASSWORD', raising=False)
    assert authed(base + '/', None)[0] == 200


def test_a_password_protects_pages_and_api(base, monkeypatch):
    monkeypatch.setenv('FLIMKIT_WEB_PASSWORD', 's3cret')
    monkeypatch.delenv('FLIMKIT_WEB_USER', raising=False)
    status, headers = authed(base + '/', None)
    assert status == 401
    assert headers['WWW-Authenticate'].startswith('Basic')
    assert authed(base + '/api/browse', login('flimkit', 'wrong'))[0] == 401
    assert authed(base + '/api/browse', login('someone', 's3cret'))[0] == 401
    assert authed(base + '/', login('flimkit', 's3cret'))[0] == 200
    status, headers, body = request(base + '/api/action', {'name': 'about'})
    assert status == 401


def test_the_login_user_can_be_changed(base, monkeypatch):
    monkeypatch.setenv('FLIMKIT_WEB_PASSWORD', 's3cret')
    monkeypatch.setenv('FLIMKIT_WEB_USER', 'lab')
    assert authed(base + '/', login('lab', 's3cret'))[0] == 200
    assert authed(base + '/', login('flimkit', 's3cret'))[0] == 401


def test_healthz_needs_no_password(base, monkeypatch):
    monkeypatch.setenv('FLIMKIT_WEB_PASSWORD', 's3cret')
    status, headers, body = request(base + '/healthz')
    assert status == 200
    assert body == b'ok'


def test_environment_overrides_the_address(monkeypatch):
    monkeypatch.setenv('FLIMKIT_WEB_HOST', '0.0.0.0')
    monkeypatch.setenv('FLIMKIT_WEB_PORT', '14500')
    assert server._address() == ('0.0.0.0', 14500)
    assert server.url() == 'http://127.0.0.1:14500'
