# flimkit-web-ui

A browser front end for [FLIMKit](https://github.com/FLIMKit/FLIMKit). Start FLIMKit, open `http://127.0.0.1:8765`, and every desktop mode is there in a web page: Single FOV, Tile Stitch, Phasor, Batch and the Machine IRF builder, plus the project browser, synthetic data generator, preferences and plugin manager.

It is an add-on, not a second copy of the app. The page drives the desktop window's own form variables and presses its own buttons, so a fit started from the browser runs through exactly the same code path as one started from the desktop, and the two stay in sync.

## Install

```
pip install flimkit-web-ui
```

Install it into the same Python environment FLIMKit runs from. FLIMKit finds it through the `flimkit.plugins` entry point, so there is nothing else to wire up. On the next start the server comes up automatically and **Tools > Open Web UI** opens it in your browser.

Verify the install with:

```bash
python -c "import flimkit_web_ui; print('ok')"
```

Tested with FLIMKit 0.13.4.

## What is in the page

| Tab | What you can do |
|---|---|
| **Single FOV** | Pick a file or z-stack, all eight IRF methods, fit model and components, fit window, masking, pile-up and background correction, run and cancel the fit. The live preview shows intensity, lifetime, decay and residuals, with the colour scale, view and τ weighting controls and the z-slider. |
| **ROI analysis** | Draw rectangle, ellipse, polygon and freehand regions straight onto the preview, rename, delete, import and export GeoJSON and CSV, and fit an ROI decay with the fit plot and table shown in the page. |
| **Tile Stitch** | All four pipelines (stitch only, stitch and fit, per-tile fit, multidimensional series), per-pixel map exports, tile registration and per-tile IRFs. |
| **Phasor** | Load a PTU or resume a session, click the phasor plot to place cursors, drag them, polygon cursors, radius and ratio, phasor filters, Find Peaks (with one-click cursors on each peak), FRET trajectory and donor FRET fit, cursor-gated decay fit, save the session. |
| **Batch** | Multi-tile ROI, single FOV and timelapse batches, with every export option and the timelapse reference lifetimes. |
| **Machine IRF** | Build a machine IRF from PTU and XLSX pairs and see the result plotted. |
| **Results** | The run log, fit summary table and CSV, image export (PNG, OME-TIFF, OME-Zarr), the output image browser, session save and restore, and expert settings. |
| **Tools** | Project folder browser and recent files, synthetic PTU generator, preferences, plugins, about, update check and error logs. |

Files are chosen with a file browser in the page, which lists folders on the machine FLIMKit is running on. Anything the desktop would offer as a save dialog is either written to the path you give or downloaded by the browser.

## How it behaves

- **One app, shared state.** There is one FLIMKit window behind the page. Several tabs or people can open it, but they all control the same form and the same results, and the last edit wins. Only one fit runs at a time.
- **Dialogs move to the page while you use it.** While a web page is open and has been used in the last 30 minutes, FLIMKit's desktop pop-ups (errors, warnings, "missing input", channel and frequency prompts) appear as notices in the page instead of blocking the desktop. Close the tab and the desktop behaves normally again.
- **Progress windows still appear on the desktop.** The page mirrors their progress and can cancel them.

## Security

The server listens on `127.0.0.1` only and has no authentication. Anyone who can reach it can browse your files and run FLIMKit, so do not expose it to a network you do not trust.

The address is read from the `plugin:web_ui` section of `~/.flimkit/config.json`:

```json
{
  "plugin:web_ui": {
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

## Working on it

```bash
pip install --no-deps 'flimkit @ git+https://github.com/FLIMKit/FLIMKit'
pip install -e '.[test]'
pytest -q
```

The tests are headless: they check the plugin registers, the dialog and threading bridge, the API helpers and the HTTP server against a stand-in app, so they need no display and no FLIMKit scientific stack.

| File | What it does |
|---|---|
| `flimkit_web_ui/__init__.py` | Registers the startup hook that starts the server and the **Tools > Open Web UI** entry |
| `flimkit_web_ui/server.py` | The HTTP server and its routes |
| `flimkit_web_ui/bridge.py` | Runs calls on the Tk thread, routes desktop dialogs to the page, tracks progress windows and renders the desktop's figures |
| `flimkit_web_ui/api.py` | Form fields, app state, Single FOV, ROIs, results and expert settings |
| `flimkit_web_ui/api_modes.py` | Tile Stitch, Batch, Machine IRF, Phasor, projects and the tools menu |
| `flimkit_web_ui/page.html`, `core.js`, `fov.js`, `modes.js` | The page |

## Releasing

Push a tag like `v0.1.0`. The `publish` workflow builds the package and uploads it to PyPI through trusted publishing, and the `release` workflow attaches the wheel and sdist to a GitHub release.

## Licence

MIT, same as FLIMKit.
