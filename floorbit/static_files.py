"""How /static/ files leave the server: compressed, and cached for good where the name changes.

Without a proxy that compresses (k3s' Traefik doesn't by default), every first visit downloaded
about 1 MB of JavaScript and CSS as is; gzipped it is about a third. Vite puts a hash of the content
in every name under /static/app/assets/, so the browser may keep those for a year and never ask
again. The other static files keep their names across releases: the browser asks each time and gets
a 304 when nothing changed.

Only static files are compressed, not pages or API answers: those can carry a secret next to text
an attacker chose, which compression would leak (BREACH).
"""
import gzip
import os
import threading

from flask import request
from werkzeug.security import safe_join

HASHED = 'app/assets/'
FOREVER = 'public, max-age=31536000, immutable'
TEXT = ('text/', 'application/javascript', 'application/json', 'image/svg+xml')
SMALLEST = 1024          # bytes: below this gzip saves less than its own headers
LEVEL = 6
CACHE_LIMIT = 64 * 1024 * 1024   # bytes of gzipped files kept in memory

_cache = {}              # (path, mtime, size) -> gzipped bytes
_cache_bytes = [0]
_lock = threading.Lock()


def _compressible(response):
    kind = response.mimetype or ''
    return kind.startswith(TEXT) or kind.endswith(('+json', '+xml'))


def _gzipped(path):
    try:
        info = os.stat(path)
    except OSError:
        return None
    key = (path, info.st_mtime_ns, info.st_size)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    with open(path, 'rb') as f:
        body = gzip.compress(f.read(), compresslevel=LEVEL, mtime=0)
    with _lock:
        if _cache_bytes[0] + len(body) > CACHE_LIMIT:
            _cache.clear()
            _cache_bytes[0] = 0
        _cache[key] = body
        _cache_bytes[0] += len(body)
    return body


def init_static_files(app):
    """Register first: Flask runs after_request hooks last-registered first, so this one sees the
    answer the others made."""

    @app.after_request
    def static_files(response):
        if request.endpoint != 'static':
            return response
        name = (request.view_args or {}).get('filename') or ''
        if response.status_code in (200, 304) and name.startswith(HASHED):
            response.headers['Cache-Control'] = FOREVER
        if response.status_code != 200 or not _compressible(response):
            return response
        response.vary.add('Accept-Encoding')
        if 'gzip' not in request.accept_encodings or response.headers.get('Content-Encoding'):
            return response
        if request.range or (response.content_length or 0) < SMALLEST:
            return response
        path = safe_join(app.static_folder, name)
        body = _gzipped(path) if path else None
        if body is None:
            return response
        old = response.response
        if hasattr(old, 'close'):
            old.close()            # the open file send_file handed over
        response.direct_passthrough = False
        response.set_data(body)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers.pop('Accept-Ranges', None)
        # The same tag for both encodings, so weak: a 304 still answers either copy.
        etag, weak = response.get_etag()
        if etag and not weak:
            response.set_etag(etag, weak=True)
        return response
