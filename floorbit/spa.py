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


def assets(entry=ENTRY):
    """{'js': [...], 'css': [...]} for a build entry, or None when the app isn't built."""
    path = _manifest_path()
    cache = current_app.extensions.setdefault('floorbit_spa', {})
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if cache.get('mtime') != mtime:
        with open(path, encoding='utf-8') as f:
            cache.update(mtime=mtime, manifest=json.load(f), assets={})
    if entry not in cache['assets']:
        cache['assets'][entry] = _collect(cache['manifest'], entry)
    return cache['assets'][entry]


def _collect(manifest, entry):
    item = manifest.get(entry) or {}
    css, preload, seen, todo = [], [], set(), [entry]
    # Shared chunks bring their own styles.
    while todo:
        name = todo.pop(0)
        if name in seen:
            continue
        seen.add(name)
        chunk = manifest.get(name, {})
        css += [c for c in chunk.get('css', []) if c not in css]
        if name != entry and chunk.get('file') and chunk['file'] not in preload:
            preload.append(chunk['file'])
        todo += chunk.get('imports', [])
    return {
        'js': [f"/static/app/{item['file']}"] if item.get('file') else [],
        'css': [f'/static/app/{c}' for c in css],
        # The chunks the entry imports, asked for at once: without these the browser found them
        # only after the entry had arrived and been read, a whole extra round trip.
        'preload': [f'/static/app/{f}' for f in preload],
    }


def render(title, page=None):
    """The React page for this request; 503 with build instructions when there is no build.

    ``page`` is for answers the app draws instead of the route's own page, such as "not allowed":
    a dict with ``kind`` that frontend/src/lib/serverPage.ts reads."""
    built = assets()
    return render_template('spa.html', title=title, assets=built, page=page), (200 if built else 503)
