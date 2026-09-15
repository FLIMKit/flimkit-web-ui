import webbrowser

from flimkit.plugins import startup, tool

from . import server

FLIMKIT_PLUGIN_API = 1


@startup(id='web_ui', order=900)
def launch_web_ui(app):
    server.start(app)


@tool(id='open_web_ui', label='Open Web UI', menu='Tools', order=850)
def open_web_ui(app):
    server.start(app)
    webbrowser.open(server.url())
