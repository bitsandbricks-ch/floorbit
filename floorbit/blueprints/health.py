"""The service health wall (issue #28). The checks come from health plugins (floorbit/health.py).

- ``GET /health``: the wall, for the ops screen or a kiosk browser (``?theme=`` sticks per screen).
- ``GET /api/health``: every service with its status, summary and metrics, and until when it is
  muted (issue #260; who muted it and why stay on the Problems page).
- ``POST /api/health/check``: ask every health plugin now instead of waiting for the next poll.
- ``GET /healthz``: "the app answers", for the Docker healthcheck, Kubernetes and load balancers.
  Open without signing in, so it says little: whether the database answers (``database``: up or
  down), and for how long it hasn't. It stays 200 while the database is away, because Floorbit
  keeps serving and a restart wouldn't bring the database back; ``?strict=1`` answers 503 then,
  for a load balancer with another instance to send people to (docs/database.md).
"""
import errno
import time

from flask import Blueprint, current_app, jsonify, request

from integrations import alerting

from .. import database, i18n, spa

bp = Blueprint('health', __name__)


def _wall():
    return current_app.extensions['floorbit_health']


@bp.route('/healthz')
def alive():
    db = database.status()
    if db['ok']:
        return jsonify({'ok': True, 'database': 'up'})
    body = {'ok': True, 'database': 'down', 'down_for': round(time.time() - db.get('since', time.time())),
            'retry_in': db.get('retry_in')}
    if request.args.get('strict'):
        return jsonify({**body, 'ok': False}), 503
    return jsonify(body)


alive._auth_public = True   # what auth.public_endpoint sets

UNAVAILABLE = ("The database isn't answering right now. Floorbit keeps trying; until it's back, "
               "pages show what was last read and changes can't be saved.")


def database_unavailable(exc):
    """A request that needed the database while it is away: 503 and a clear word, not a 500. The
    API answers JSON (the app shows it and its banner); a page answers a short page that reloads
    itself."""
    lang = i18n.language(request.headers.get('Accept-Language'))
    wants_json = request.path.startswith('/api/') or request.accept_mimetypes.best == 'application/json'
    if wants_json:
        resp = jsonify({'error': UNAVAILABLE, 'code': 'database_unavailable'})
    else:
        # Straight from Jinja: the context processors (theme, demo banner, plugins) need the database.
        resp = current_app.make_response(current_app.jinja_env.get_template('unavailable.html').render(
            lang='de' if lang.startswith('de') else 'en',
            title=i18n.translate('Database unavailable', lang), text=i18n.translate(UNAVAILABLE, lang),
            retry=i18n.translate('Trying again by itself…', lang)))
    resp.status_code = 503
    resp.headers['Retry-After'] = '10'
    return resp


DISK_FULL = ("Floorbit's disk is full, so this change was not saved. What was saved before is safe. "
             'Free some space on the server (or give the volume more), then try again.')
DISK_READ_ONLY = ("Floorbit's state folder is read-only, so this change was not saved. "
                  'Mount it writable (docs/install.md), then try again.')
_DISK_ERRORS = {errno.ENOSPC: DISK_FULL, errno.EDQUOT: DISK_FULL, errno.EROFS: DISK_READ_ONLY}
_disk_logged = set()


def disk_unwritable(exc):
    """A save that hit a full or read-only disk: a clear 507 instead of an HTML 500 and a traceback
    per click. The store never leaves half a file (floorbit/store.py), so nothing earlier is lost."""
    text = _DISK_ERRORS.get(getattr(exc, 'errno', None))
    if text is None:
        raise exc   # any other OSError stays a bug to see
    if exc.errno not in _disk_logged:   # once per kind, not on every click while it lasts
        _disk_logged.add(exc.errno)
        print(f'[store] Saving failed: {exc.strerror} ({getattr(exc, "filename", None) or "state folder"}). '
              'Pages still show what was saved; changes fail until there is space again.', flush=True)
    resp = jsonify({'error': text, 'code': 'disk_full' if text is DISK_FULL else 'disk_read_only'})
    resp.status_code = 507
    return resp


@bp.route('/health')
def health_page():
    return spa.render('Service health')


def _with_mutes(wall):
    muted = alerting.mutes()
    # The tiles' own words in the reader's language (issue #467); a plugin's text without a German
    # one in de-CH.json stays as the plugin wrote it.
    lang = i18n.language(request.headers.get('Accept-Language'))
    checks = [{**c, 'summary': i18n.translate(c.get('summary'), lang),
               'metrics': [{**m, 'label': i18n.translate(m.get('label'), lang)} for m in c.get('metrics') or []],
               'muted_until': (muted.get(alerting.service_key(c['id'])) or {}).get('until')}
              for c in wall.get('checks') or []]
    return {**wall, 'checks': checks}


@bp.route('/api/health', methods=['GET'])
def health():
    return jsonify(_with_mutes(_wall().fresh()))


@bp.route('/api/health/check', methods=['POST'])
def check_now():
    _wall().poll_once()
    return jsonify(_with_mutes(_wall().snapshot()))


TOO_LARGE = 'That is too much data for one request.'


def too_large(exc):
    """413 as JSON on the API, so the pages can show it; elsewhere the plain error page."""
    if not request.path.startswith('/api/'):
        return exc
    return jsonify({'error': TOO_LARGE, 'code': 'too_large'}), 413
