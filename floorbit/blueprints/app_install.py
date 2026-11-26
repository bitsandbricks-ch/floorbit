"""Floorbit as an app on a phone's home screen (Mike, 2026-11-26: an installable web app, no store).

- ``GET /manifest.webmanifest``: the name, icons and colours Android and iOS show once installed.
- ``GET /sw.js``: the service worker (static/sw.js). It has to come from the site's root to look
  after every page, and is asked for again on each visit so a new one is picked up.

Both are open without signing in: the browser fetches them without the session cookie.
"""
from flask import Blueprint, current_app, jsonify, send_from_directory

from auth import public_endpoint

bp = Blueprint('app_install', __name__)

BACKGROUND = '#0b0b0f'   # the brand's page colour (static/css/brand/tokens.css --theme-bg)


@bp.route('/manifest.webmanifest')
@public_endpoint
def manifest():
    settings = current_app.extensions.get('floorbit_settings')
    bg = (settings.get('theme.background') if settings else '') or BACKGROUND
    icon = '/static/brand/icon-{}.png'
    res = jsonify({
        'name': 'Floorbit',
        'short_name': 'Floorbit',
        'id': '/',
        'start_url': '/',
        'scope': '/',
        'display': 'standalone',
        'background_color': bg,
        'theme_color': bg,
        'icons': [
            {'src': icon.format(192), 'sizes': '192x192', 'type': 'image/png'},
            {'src': icon.format(512), 'sizes': '512x512', 'type': 'image/png'},
            {'src': icon.format('maskable-512'), 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    })
    res.mimetype = 'application/manifest+json'
    return res


@bp.route('/sw.js')
@public_endpoint
def service_worker():
    res = send_from_directory(current_app.static_folder, 'sw.js', mimetype='text/javascript', max_age=0)
    res.headers['Cache-Control'] = 'no-cache'
    return res
