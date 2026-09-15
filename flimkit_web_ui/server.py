import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from flimkit.plugins import plugin_config

from . import api, bridge

_HERE = os.path.dirname(os.path.abspath(__file__))
_STATIC = {
    '/': ('page.html', 'text/html; charset=utf-8'),
    '/core.js': ('core.js', 'application/javascript; charset=utf-8'),
    '/fov.js': ('fov.js', 'application/javascript; charset=utf-8'),
    '/modes.js': ('modes.js', 'application/javascript; charset=utf-8'),
}
_server = None
_lock = threading.Lock()


def _address():
    cfg = plugin_config('web_ui')
    return cfg.get('host', '127.0.0.1'), int(cfg.get('port', 8765) or 8765)


def url():
    host, port = _address()
    return 'http://' + host + ':' + str(port)


def make_handler(app):

    class Handler(BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):
            pass

        def _send(self, status, body, ctype, extra=None):
            self.send_response(status)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload, status=200):
            self._send(status, json.dumps(payload, default=str).encode('utf-8'), 'application/json')

        def do_GET(self):
            parsed = urlparse(self.path)
            q = parse_qs(parsed.query)
            path = parsed.path
            try:
                if path in _STATIC:
                    nam, ctype = _STATIC[path]
                    with open(_HERE + os.sep + nam, 'rb') as f:
                        self._send(200, f.read(), ctype)
                elif path == '/api/state':
                    self._json(api.get_state(app))
                elif path == '/api/fig.png':
                    png, geom, rev = bridge.render(app, q.get('key', ['fov'])[0])
                    self._send(200, png, 'image/png', {'X-Geom': json.dumps(geom), 'X-Rev': str(rev)})
                elif path == '/api/fit.png':
                    ids = [int(x) for x in q.get('ids', [''])[0].split(',') if x != '']
                    result = api.fit_result(app, q.get('src', ['roi'])[0], ids)
                    self._send(200, api.fit_png(result), 'image/png')
                elif path == '/api/browse':
                    self._json(api.list_dir(q.get('dir', ['~'])[0]))
                elif path == '/api/result_image':
                    self._send(200, api.result_image(app, int(q.get('i', ['0'])[0])), 'image/png')
                else:
                    self._send(404, b'not found', 'text/plain')
            except TimeoutError as exc:
                self._json({'ok': False, 'busy': True, 'error': str(exc), 'notes': bridge.drain_notes()}, status=503)
            except ValueError as exc:
                self._json({'ok': False, 'error': str(exc)}, status=404)
            except Exception as exc:
                self._json({'ok': False, 'error': str(exc)}, status=500)

        def do_POST(self):
            length = int(self.headers.get('Content-Length', 0) or 0)
            try:
                payload = json.loads(self.rfile.read(length) or b'{}')
                if self.path == '/api/set':
                    self._json({'ok': True, 'notes': api.set_fields(app, payload)})
                elif self.path == '/api/action':
                    out = api.run_action(app, payload.get('name', ''), payload.get('args') or {})
                    out['ok'] = True
                    self._json(out)
                else:
                    self._send(404, b'not found', 'text/plain')
            except Exception as exc:
                self._json({'ok': False, 'error': str(exc), 'notes': bridge.drain_notes()}, status=400)

    return Handler


def start(app):
    global _server
    with _lock:
        if _server is not None:
            return _server
        bridge.install_dialogs()
        bridge.install_roi_hooks()
        bridge.hook_progress()
        server = ThreadingHTTPServer(_address(), make_handler(app))
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        _server = server
        print('[web_ui] serving ' + url())
        return server
