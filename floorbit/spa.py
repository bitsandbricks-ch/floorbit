"""The React app (frontend/), built into static/app/ by ``npm run build``.

Flask renders templates/spa.html for the pages that moved to React, with the theme from the
server (preset, colours, light/dark lock) on <html> before any script runs, and the script and
style tags from Vite's manifest. Without a build, the page says how to make one.
"""
import json
import os

from flask import current_app, render_template

ENTRY = 'index.html'


def _manifest_path():
    return os.path.join(current_app.static_folder, 'app', '.vite', 'manifest.json')


def assets():
    """{'js': [...], 'css': [...]} for the entry, or None when the app isn't built."""
    path = _manifest_path()
    cache = current_app.extensions.setdefault('floorbit_spa', {})
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if cache.get('mtime') != mtime:
        with open(path, encoding='utf-8') as f:
            manifest = json.load(f)
        entry = manifest.get(ENTRY) or {}
        css = list(entry.get('css', []))
        for name in entry.get('imports', []):
            css += manifest.get(name, {}).get('css', [])
        cache.update(mtime=mtime, assets={
            'js': [f"/static/app/{entry['file']}"] if entry.get('file') else [],
            'css': [f'/static/app/{c}' for c in css],
        })
    return cache['assets']


def render(title):
    """The React page for this request; 503 with build instructions when there is no build."""
    built = assets()
    return render_template('spa.html', title=title, assets=built), (200 if built else 503)
