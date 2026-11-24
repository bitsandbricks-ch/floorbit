"""Several dashboard tiles in one request (issue #1300).

- ``GET /api/dashboard/widgets?u=<tile url>&u=...``: ``{"results": [{"status", "body"}, ...]}``, in the
  order asked.

A dashboard opened 30 tiles as 30 requests at once. With one gunicorn worker they all queued for the
same process, and each one paid for sign-in, the event choice and the other per-request hooks again.
Each tile here still goes through its own route, with its own permission check, inside this one
request; only tile addresses are taken, so this can't reach anything a tile can't. Sources several
tiles read (floorbit/batch_share.py) are read once per batch.
"""
import re
from urllib.parse import urlsplit

from flask import Blueprint, current_app, jsonify, request

from ..batch_share import batch

bp = Blueprint('widget_batch', __name__)

MAX_TILES = 64
TILE_PATHS = (
    re.compile(r'/api/dashboard/floorbit/[\w-]+'),
    re.compile(r'/api/plugins/[\w.-]+/widgets/[\w.-]+'),
)


def _tile_path(url):
    parts = urlsplit(url or '')
    if parts.scheme or parts.netloc or parts.fragment:
        return None
    if not any(p.fullmatch(parts.path) for p in TILE_PATHS):
        return None
    return parts.path, parts.query


def _one(path, query):
    """The tile's own route, answered as if it had been asked on its own."""
    environ = dict(request.environ)
    environ.update(PATH_INFO=path, QUERY_STRING=query, REQUEST_METHOD='GET', CONTENT_LENGTH='0')
    environ.pop('werkzeug.request', None)
    app = current_app._get_current_object()
    # Its own app context: ``g`` is per tile then, so the hooks that keep state there (the event
    # picked, its reset at teardown) don't overwrite this request's.
    with app.app_context(), app.request_context(environ):
        try:
            response = app.full_dispatch_request()
        except Exception:
            current_app.logger.exception('dashboard tile %s failed', path)
            return {'status': 500, 'body': {'error': 'This tile failed; the server log has why.'}}
    body = response.get_json(silent=True)
    response.close()
    return {'status': response.status_code, 'body': body if body is not None else {}}


@bp.route('/api/dashboard/widgets', methods=['GET'])
def widgets():
    urls = request.args.getlist('u')
    if not urls:
        return jsonify({'error': 'Name at least one tile.'}), 400
    if len(urls) > MAX_TILES:
        return jsonify({'error': f'At most {MAX_TILES} tiles at once.'}), 400
    results = []
    # Tiles that read the same source (the traffic snapshot, the flows, DNS) read it once here.
    with batch():
        for url in urls:
            found = _tile_path(url)
            if found is None:
                results.append({'status': 400, 'body': {'error': 'Not a tile address.'}})
                continue
            results.append(_one(*found))
    return jsonify({'results': results})
