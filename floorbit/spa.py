"""The React app (frontend/), built into static/app/ by ``npm run build``.

Flask renders templates/spa.html for the pages that moved to React, with the theme from the
server (preset, colours, light/dark lock) on <html> before any script runs, and the script and
style tags from Vite's manifest. Without a build, the page says how to make one.
"""
import json
import os

from flask import current_app, render_template

ENTRY = 'index.html'
# What the pages inside the app shell fetch on top of the entry: the shell and the rest of the
# English texts (frontend/src/App.tsx). Sign-in, check-in and the public pages don't (issue #1293).
SHELL = ('src/components/Layout.tsx', 'src/i18n/english.ts')


def _manifest_path():
    return os.path.join(current_app.static_folder, 'app', '.vite', 'manifest.json')


def assets(entry=ENTRY, shell=True):
    """{'js': [...], 'css': [...], 'preload': [...]} for a build entry, or None when the app isn't
    built. ``shell``: also what the pages inside the app shell load next, asked for at once."""
    path = _manifest_path()
    cache = current_app.extensions.setdefault('floorbit_spa', {})
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    if cache.get('mtime') != mtime:
        with open(path, encoding='utf-8') as f:
            cache.update(mtime=mtime, manifest=json.load(f), assets={})
    key = (entry, shell)
    if key not in cache['assets']:
        cache['assets'][key] = _collect(cache['manifest'], entry, SHELL if shell else ())
    return cache['assets'][key]


def _collect(manifest, entry, more=()):
    item = manifest.get(entry) or {}
    css, preload, seen, todo = [], [], set(), [entry, *(m for m in more if m in manifest)]
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
        # The chunks the entry imports (and the shell's), asked for at once: without these the
        # browser found them only after the entry had arrived and been read, a whole extra round trip.
        'preload': [f'/static/app/{f}' for f in preload],
    }


def render(title, page=None, shell=True):
    """The React page for this request; 503 with build instructions when there is no build.

    ``page`` is for answers the app draws instead of the route's own page, such as "not allowed":
    a dict with ``kind`` that frontend/src/lib/serverPage.ts reads. ``shell=False`` for the pages
    outside the app shell (sign-in, check-in, the public pages), which then load less."""
    built = assets(shell=shell)
    return render_template('spa.html', title=title, assets=built, page=page), (200 if built else 503)
